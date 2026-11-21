"""Ship the lake to Azure Data Lake Storage Gen2. Dormant unless CARELAKE_SINK=adls.

Layout in the account (one filesystem per layer, so access can differ per layer):

    raw/<table>/<cohort>.parquet      raw/_rejects/<cohort>.parquet     raw/_manifest/<cohort>.json
    curated/<table>/<cohort>.parquet  curated/_tally/<cohort>.parquet
    serving/<mart>.parquet            feeds/status.json, feeds/history.json
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from carelake.settings import Paths

LAYERS = ("raw", "curated", "serving", "feeds")


class Shipper(Protocol):
    def send(self, filesystem: str, remote: str, local: Path) -> None: ...


class AdlsShipper:
    def __init__(self, account: str, key: str | None):
        from azure.storage.filedatalake import DataLakeServiceClient

        url = f"https://{account}.dfs.core.windows.net"
        if key:
            self._client = DataLakeServiceClient(account_url=url, credential=key)
        else:
            from azure.identity import DefaultAzureCredential

            self._client = DataLakeServiceClient(account_url=url, credential=DefaultAzureCredential())
        self._ready: set[str] = set()

    def send(self, filesystem: str, remote: str, local: Path) -> None:
        fs = self._client.get_file_system_client(filesystem)
        if filesystem not in self._ready:
            if not fs.exists():
                fs.create_file_system()
            self._ready.add(filesystem)
        with local.open("rb") as data:
            fs.get_file_client(remote).upload_data(data, overwrite=True)


def manifest(paths: Paths) -> list[tuple[str, str, Path]]:
    items: list[tuple[str, str, Path]] = []
    for layer, root in (("raw", paths.raw), ("curated", paths.curated), ("serving", paths.serving)):
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if not (p.is_file() and p.suffix in (".parquet", ".json")):
                continue
            rel = p.relative_to(root)
            # raw/<cohort>/fhir/*.json are the source bundles, gigabytes of identified
            # JSON; only the parquet tables, rejects and manifests leave the laptop
            if layer == "raw" and (root / rel.parts[0] / "fhir").is_dir():
                continue
            items.append((layer, rel.as_posix(), p))
    if paths.feeds.exists():
        items += [("feeds", p.name, p) for p in sorted(paths.feeds.glob("*.json"))]
    return items


def ship(
    paths: Paths,
    sink: str,
    account: str,
    key: str,
    shipper: Shipper | None = None,
    layers: Iterable[str] | None = None,
    say=print,
) -> int:
    if sink != "adls":
        say("sink is files; nothing shipped to Azure (set CARELAKE_SINK=adls)")
        return 0
    if shipper is None:
        if not account:
            raise RuntimeError("CARELAKE_ADLS_ACCOUNT is required when CARELAKE_SINK=adls")
        shipper = AdlsShipper(account, key or None)
    wanted = set(layers) if layers else set(LAYERS)
    n = 0
    for fs, remote, local in manifest(paths):
        if fs in wanted:
            shipper.send(fs, remote, local)
            n += 1
    say(f"shipped {n} files to ADLS Gen2 ({account or 'test double'})")
    return n
