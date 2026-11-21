"""Synthea, pinned three ways (population seed, clinician seed, reference date)
so a cohort is a pure function of its label."""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from carelake.settings import SYNTHEA_RELEASE, SYNTHEA_SHA256, SYNTHEA_URL, Paths, java_opts


@dataclass(frozen=True)
class Cohort:
    label: str
    seed: int
    size: int
    as_of: date
    state: str = "Illinois"


def weekly_cohort(day: date, size: int) -> Cohort:
    """One cohort per ISO week, labelled w<year><week>, dated on its Monday."""
    y, w, _ = day.isocalendar()
    return Cohort(
        label=f"w{y}{w:02d}", seed=int(f"{y}{w:02d}"), size=size, as_of=date.fromisocalendar(y, w, 1)
    )


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_jar(paths: Paths, say=print) -> Path:
    jar = paths.jar
    if jar.exists() and digest(jar) == SYNTHEA_SHA256:
        return jar
    jar.parent.mkdir(parents=True, exist_ok=True)
    say(f"fetching Synthea {SYNTHEA_RELEASE}")
    part = jar.with_suffix(".download")
    urllib.request.urlretrieve(SYNTHEA_URL, part)  # noqa: S310 - pinned https URL
    if digest(part) != SYNTHEA_SHA256:
        part.unlink(missing_ok=True)
        raise RuntimeError("Synthea jar does not match the pinned checksum")
    part.replace(jar)
    return jar


def cohort_dir(paths: Paths, label: str) -> Path:
    return paths.raw / label


def manifest_path(paths: Paths, label: str) -> Path:
    return cohort_dir(paths, label) / "manifest.json"


def run_synthea(paths: Paths, cohort: Cohort, say=print) -> Path:
    out = cohort_dir(paths, cohort.label)
    if manifest_path(paths, cohort.label).exists():
        say(f"{cohort.label}: already generated")
        return out
    jar = fetch_jar(paths, say)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        "java",
        *java_opts(),
        "-jar",
        str(jar),
        "-p",
        str(cohort.size),
        "-s",
        str(cohort.seed),
        "-cs",
        str(cohort.seed),
        "-r",
        cohort.as_of.strftime("%Y%m%d"),
        f"--exporter.baseDirectory={out.as_posix()}/",
        "--exporter.fhir.export=true",
        "--exporter.hospital.fhir.export=false",
        "--exporter.practitioner.fhir.export=false",
        "--exporter.csv.export=false",
        "--generate.only_alive_patients=false",
        cohort.state,
    ]
    say(f"{cohort.label}: Synthea, {cohort.size} patients, seed {cohort.seed}, {cohort.state}")
    with (out / "synthea.log").open("w", encoding="utf-8") as log:
        rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False).returncode
    if rc != 0:
        raise RuntimeError(f"Synthea returned {rc}; see {out / 'synthea.log'}")
    bundles = sorted((out / "fhir").glob("*.json"))
    if not bundles:
        raise RuntimeError("no bundles were written")
    manifest_path(paths, cohort.label).write_text(
        json.dumps(
            {
                "label": cohort.label,
                "seed": cohort.seed,
                "requested": cohort.size,
                "bundles": len(bundles),
                "as_of": cohort.as_of.isoformat(),
                "state": cohort.state,
                "synthea": SYNTHEA_RELEASE,
                "jar_sha256": SYNTHEA_SHA256,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    say(f"{cohort.label}: {len(bundles)} bundles")
    return out


def as_of_for(paths: Paths, label: str) -> date:
    m = manifest_path(paths, label)
    if m.exists():
        return date.fromisoformat(json.loads(m.read_text(encoding="utf-8"))["as_of"])
    return date.today()


def labels(paths: Paths) -> list[str]:
    if not paths.raw.exists():
        return []
    return sorted(p.name for p in paths.raw.iterdir() if (p / "fhir").is_dir())
