"""Refuse to publish feeds that the page could not read.
Usage: verify_feeds.py web/feeds/status.json web/feeds/history.json"""

from __future__ import annotations

import json
import sys
from pathlib import Path

NEED_STATUS = ("built_at", "synthetic", "cohorts", "counts", "scrub", "pairs", "care_gaps", "dbt")
NEED_COUNTS = ("patients", "encounters", "diagnoses", "results", "rejects")
NEED_POINT = ("week", "patients", "encounters", "rejects")
FORBIDDEN = ("ssn", "surname", "forenames", "street", "tel", "mail", "dob")


def check(status_path: str, history_path: str) -> list[str]:
    faults: list[str] = []
    s = json.loads(Path(status_path).read_text(encoding="utf-8"))
    faults += [f"status.json lacks {k}" for k in NEED_STATUS if k not in s]
    faults += [f"status.counts lacks {k}" for k in NEED_COUNTS if k not in s.get("counts", {})]
    if s.get("synthetic") is not True:
        faults.append("status.synthetic must be true")
    if not s.get("counts", {}).get("patients"):
        faults.append("no patients in the lake")
    dbt = s.get("dbt", {})
    if not dbt.get("tests") or dbt.get("failed"):
        faults.append(f"dbt did not pass cleanly: {dbt}")
    h = json.loads(Path(history_path).read_text(encoding="utf-8"))
    if not isinstance(h, list) or not h:
        faults.append("history.json must be a non-empty list")
    else:
        faults += [f"history point lacks {k}" for k in NEED_POINT if k not in h[-1]]
        weeks = [p.get("week") for p in h]
        if weeks != sorted(set(weeks)):
            faults.append("history.json is not sorted and unique by week")
    text = json.dumps(s) + json.dumps(h)
    faults += [f"feed names a column called {c}" for c in FORBIDDEN if f'"{c}"' in text]
    return faults


if __name__ == "__main__":
    problems = check(sys.argv[1], sys.argv[2])
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    s = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(f"feeds ok: {s['counts']['patients']} patients")
