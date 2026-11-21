"""Raw to curated: the one reader of raw, the one writer of curated."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pyarrow as pa

from carelake._parquet import RowGroupWriter, rows
from carelake.generate import as_of_for
from carelake.schemas import TableSchema, load_all
from carelake.scrub import SCRUB_VERSION, Scrubber, Tally, curated_schema
from carelake.settings import Paths

TALLY_SCHEMA = pa.schema(
    [
        pa.field("cohort", pa.string()),
        pa.field("table_name", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("scrubbed_at", pa.timestamp("us", tz="UTC")),
        pa.field("scrub_version", pa.int32()),
        pa.field("rows", pa.int64()),
        pa.field("dropped", pa.string()),
        pa.field("hashed", pa.int64()),
        pa.field("offset", pa.int64()),
        pa.field("zip3", pa.int64()),
        pa.field("zip3_small", pa.int64()),
        pa.field("over_89", pa.int64()),
        pa.field("swept", pa.int64()),
    ]
)


def curate_cohort(
    paths: Paths, label: str, secret: str, say=print, schemas: dict[str, TableSchema] | None = None
) -> dict:
    schemas = schemas or load_all()
    t0 = time.monotonic()
    scrubber = Scrubber(secret, as_of_for(paths, label))
    tallies: dict[str, Tally] = {}
    for table, s in schemas.items():
        src = paths.raw / table / f"{label}.parquet"
        if not src.exists():
            raise FileNotFoundError(f"{src} is missing: land the cohort first")
        tally = Tally()
        w = RowGroupWriter(paths.curated / table / f"{label}.parquet", curated_schema(s))
        for row in rows(src, columns=s.columns + ["_cohort"]):
            w.put(scrubber.row(s, row, tally))
        w.finish()
        tallies[table] = tally

    done = datetime.now(UTC)
    tw = RowGroupWriter(paths.curated / "_tally" / f"{label}.parquet", TALLY_SCHEMA)
    for table, t in tallies.items():
        d = t.as_dict()
        tw.put(
            {
                "cohort": label,
                "table_name": table,
                "as_of": scrubber.as_of,
                "scrubbed_at": done,
                "scrub_version": SCRUB_VERSION,
                "rows": d["rows"],
                "dropped": ",".join(d["dropped"]),
                "hashed": d["hashed"],
                "offset": d["offset"],
                "zip3": d["zip3"],
                "zip3_small": d["zip3_small"],
                "over_89": d["over_89"],
                "swept": sum(d["swept"].values()),
            }
        )
    tw.finish()
    report = {
        "cohort": label,
        "scrub_version": SCRUB_VERSION,
        "as_of": scrubber.as_of.isoformat(),
        "scrubbed_at": done.isoformat(),
        "seconds": round(time.monotonic() - t0, 1),
        "tables": {t: x.as_dict() for t, x in tallies.items()},
    }
    out = paths.curated / "_tally" / f"{label}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    say(f"curated {label}: {sum(t.rows for t in tallies.values()):,} rows scrubbed in {report['seconds']}s")
    return report
