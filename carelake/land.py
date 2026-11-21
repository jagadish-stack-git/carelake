"""Bundles to the raw layer. Rows that pass their schema land in
raw/<table>/<cohort>.parquet; rows that do not go to raw/_rejects with every
problem and the resource itself, so a schema change can replay them.

The raw layer is identified (synthetic, but shaped like PHI). Only the scrubber
reads it.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa

from carelake import extract
from carelake._parquet import RowGroupWriter
from carelake.generate import cohort_dir, digest
from carelake.schemas import TableSchema, coerce, load_all
from carelake.settings import Paths

LINEAGE = [
    pa.field("_cohort", pa.string()),
    pa.field("_bundle_sha", pa.string()),
    pa.field("_landed_at", pa.timestamp("us", tz="UTC")),
    pa.field("_resource", pa.string()),
]

REJECT_SCHEMA = pa.schema(
    [
        pa.field("table_name", pa.string()),
        pa.field("schema_version", pa.int32()),
        pa.field("resource_type", pa.string()),
        pa.field("key", pa.string()),
        pa.field("pid", pa.string()),
        pa.field("cohort", pa.string()),
        pa.field("bundle_sha", pa.string()),
        pa.field("problems", pa.string()),
        pa.field("resource", pa.string()),
        pa.field("landed_at", pa.timestamp("us", tz="UTC")),
    ]
)


def raw_schema(s: TableSchema) -> pa.Schema:
    return pa.schema(list(s.arrow_raw()) + LINEAGE)


def manifest_file(paths: Paths, label: str) -> Path:
    return paths.raw / "_manifest" / f"{label}.json"


def land_cohort(paths: Paths, label: str, say=print, schemas: dict[str, TableSchema] | None = None) -> dict:
    schemas = schemas or load_all()
    bundles = sorted((cohort_dir(paths, label) / "fhir").glob("*.json"))
    if not bundles:
        raise FileNotFoundError(f"no bundles for cohort {label}")
    t0 = time.monotonic()
    now = datetime.now(UTC)
    today = now.date()

    writers = {
        t: RowGroupWriter(paths.raw / t / f"{label}.parquet", raw_schema(s)) for t, s in schemas.items()
    }
    rejects = RowGroupWriter(paths.rejects / f"{label}.parquet", REJECT_SCHEMA)
    seen: dict[str, set] = {t: set() for t in schemas}
    skipped: Counter = Counter()
    rejected: Counter = Counter()
    why: Counter = Counter()

    for n, path in enumerate(bundles, 1):
        sha = digest(path)  # the file name carries the patient's name; only the hash is kept
        per_table, skip = extract.rows_from_bundle(extract.read_bundle(path))
        skipped.update(skip)
        for table, pairs in per_table.items():
            s = schemas[table]
            for resource, row in pairs:
                problems = s.problems(row, today)
                key = row.get(s.key)
                if not problems and key in seen[table]:
                    problems = [f"{s.key}: repeated in cohort"]
                if problems:
                    rejected[table] += 1
                    for p in problems:
                        why[f"{table}/{p.split(':')[0]}"] += 1
                    rejects.put(
                        {
                            "table_name": table,
                            "schema_version": s.version,
                            "resource_type": resource["resourceType"],
                            "key": None if key is None else str(key),
                            "pid": row.get("pid"),
                            "cohort": label,
                            "bundle_sha": sha,
                            "problems": " | ".join(problems),
                            "resource": json.dumps(resource, separators=(",", ":")),
                            "landed_at": now,
                        }
                    )
                    continue
                seen[table].add(key)
                keep_resource = None if row.get("parent_oid") else json.dumps(resource, separators=(",", ":"))
                writers[table].put(
                    {
                        **coerce(s, row),
                        "_cohort": label,
                        "_bundle_sha": sha,
                        "_landed_at": now,
                        "_resource": keep_resource,
                    }
                )
        if n % 250 == 0:
            say(f"  {n}/{len(bundles)}")

    counts = {t: w.finish() for t, w in writers.items()}
    n_rejected = rejects.finish()
    report = {
        "cohort": label,
        "bundles": len(bundles),
        "landed_at": now.isoformat(),
        "seconds": round(time.monotonic() - t0, 1),
        "rows": counts,
        "rejected": dict(rejected),
        "rejected_total": n_rejected,
        "reject_reasons": dict(why.most_common()),
        "not_read": dict(skipped.most_common()),
        "schema_versions": {t: s.version for t, s in schemas.items()},
    }
    mf = manifest_file(paths, label)
    mf.parent.mkdir(parents=True, exist_ok=True)
    mf.write_text(json.dumps(report, indent=1), encoding="utf-8")
    say(
        f"raw {label}: {sum(counts.values()):,} rows, {n_rejected:,} rejected, "
        f"{sum(skipped.values()):,} resources of other types not read, {report['seconds']}s"
    )
    return report
