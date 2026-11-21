"""status.json (this build) and history.json (one point per week), the two
files the status page and my portfolio board read.

history.json is extended from whatever is currently published, so the series
survives stateless runners and needs no commits.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from typing import Any

import duckdb

from carelake import VERSION
from carelake.serve import lake_bytes
from carelake.settings import Paths


def _plain(v: Any) -> Any:
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def _q(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> dict[str, Any]:
    r = _q(con, sql)
    return r[0] if r else {}


def _share(a: Any, b: Any) -> float | None:
    return round(a / b, 4) if b else None


def status(paths: Paths, dbt: dict | None, cohorts: list[str], built_at: datetime) -> dict[str, Any]:
    with duckdb.connect(str(paths.duckdb_file)) as con:
        counts = _one(
            con,
            """
            select
              (select count(*) from marts.patient_dim where current_row) as patients,
              (select count(*) from marts.encounter_fact)                  as encounters,
              (select count(*) from marts.diagnosis_fact)                  as diagnoses,
              (select count(*) from marts.result_fact)                     as results,
              (select count(*) from marts.prescription_fact)               as prescriptions,
              (select count(*) from marts.procedure_fact)                  as procedures,
              (select count(*) from marts.vaccination_fact)                as vaccinations,
              (select coalesce(sum(n), 0) from marts.reject_log)           as rejects
            """,
        )
        reject_reasons = _q(
            con,
            "select table_name, problem, sum(n) as n from marts.reject_log "
            "group by 1, 2 order by 3 desc limit 10",
        )
        ledger = _q(con, "select * from marts.scrub_ledger order by table_name")
        risk = _one(con, "select * from marts.reidentification_risk")
        pairs = _q(
            con,
            "select bucket_a, bucket_b, both_n, lift, share from marts.chronic_pairs "
            "order by both_n desc limit 8",
        )
        gaps = _one(
            con,
            """
            select sum(diabetics) as diabetics, sum(statin_eligible) as statin_eligible,
                   sum(statin_in_year) as statin_in_year, sum(a1c_in_90d) as a1c_in_90d
            from marts.diabetes_care_gaps
            """,
        )
        by_bracket = _q(
            con,
            """
            select age_bracket, sum(diabetics) as diabetics, sum(statin_eligible) as statin_eligible,
                   sum(statin_in_year) as statin_in_year, sum(a1c_in_90d) as a1c_in_90d
            from marts.diabetes_care_gaps group by 1 order by 1
            """,
        )
        by_payer = _q(
            con,
            """
            select payer_class, sum(diabetics) as diabetics, sum(statin_eligible) as statin_eligible,
                   sum(statin_in_year) as statin_in_year, sum(a1c_in_90d) as a1c_in_90d
            from marts.diabetes_care_gaps group by 1 order by 2 desc
            """,
        )
    for r in by_bracket + by_payer:
        r["statin_share"] = _share(r["statin_in_year"], r["statin_eligible"])
        r["a1c_share"] = _share(r["a1c_in_90d"], r["diabetics"])
    cohort_info, not_read = [], {}
    for label in cohorts:
        mf = paths.raw / "_manifest" / f"{label}.json"
        if mf.exists():
            m = json.loads(mf.read_text(encoding="utf-8"))
            cohort_info.append({"label": label, "bundles": m["bundles"], "seconds": m["seconds"]})
            for k, v in m.get("not_read", {}).items():
                not_read[k] = not_read.get(k, 0) + v
    return _plain(
        {
            "built_at": built_at.isoformat(),
            "version": VERSION,
            "synthetic": True,
            "disclaimer": "All patients are Synthea output. "
            "The scrubbing is real and tested; the people are not.",
            "cohorts": cohort_info,
            "counts": counts,
            "reject_reasons": reject_reasons,
            "scrub": {"ledger": ledger, "risk": risk},
            "pairs": pairs,
            "care_gaps": {
                **{
                    k: (gaps.get(k) or 0)
                    for k in ("diabetics", "statin_eligible", "statin_in_year", "a1c_in_90d")
                },
                "statin_share": _share(gaps.get("statin_in_year") or 0, gaps.get("statin_eligible") or 0),
                "a1c_share": _share(gaps.get("a1c_in_90d") or 0, gaps.get("diabetics") or 0),
                "by_bracket": by_bracket,
                "by_payer": by_payer,
            },
            "not_read": not_read,
            "dbt": dbt or {},
            "lake_bytes": lake_bytes(paths),
            "portfolio": "https://jagadish-butukuri.vercel.app",
        }
    )


def published_history(base_url: str, timeout: float = 10.0) -> list[dict]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/feeds/history.json", timeout=timeout) as r:  # noqa: S310
            data = json.loads(r.read().decode("utf-8"))
        return data if isinstance(data, list) else []
    except (urllib.error.URLError, ValueError, TimeoutError):
        return []


def monday(day: date) -> date:
    y, w, _ = day.isocalendar()
    return date.fromisocalendar(y, w, 1)


def history_point(s: dict[str, Any], day: date, cohorts: list[str]) -> dict[str, Any]:
    c, g, risk = s["counts"], s["care_gaps"], s["scrub"]["risk"] or {}
    top = (s.get("pairs") or [{}])[0]
    return {
        "week": monday(day).isoformat(),
        "built_at": s["built_at"],
        "cohorts": cohorts,
        "patients": c.get("patients", 0),
        "encounters": c.get("encounters", 0),
        "diagnoses": c.get("diagnoses", 0),
        "results": c.get("results", 0),
        "rejects": c.get("rejects", 0),
        "statin_share": g.get("statin_share"),
        "a1c_share": g.get("a1c_share"),
        "k_min": risk.get("smallest_group"),
        "unique_share": risk.get("unique_share"),
        "top_pair": f"{top.get('bucket_a')} & {top.get('bucket_b')}" if top else None,
        "tests_ok": (s.get("dbt") or {}).get("tests_ok"),
        "tests": (s.get("dbt") or {}).get("tests"),
    }


def upsert(history: list[dict], point: dict) -> list[dict]:
    by_week = {p["week"]: p for p in history if isinstance(p, dict) and p.get("week")}
    by_week[point["week"]] = point
    return [by_week[k] for k in sorted(by_week)]


def write_feeds(
    paths: Paths, dbt: dict | None, cohorts: list[str], base_url: str, extend: bool = True, say=print
) -> dict:
    now = datetime.now(UTC)
    s = status(paths, dbt, cohorts, now)
    series = upsert(published_history(base_url) if extend else [], history_point(s, now.date(), cohorts))
    paths.feeds.mkdir(parents=True, exist_ok=True)
    (paths.feeds / "status.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    (paths.feeds / "history.json").write_text(json.dumps(series, indent=1), encoding="utf-8")
    say(f"feeds: status.json and history.json ({len(series)} week(s)) in {paths.feeds}")
    return s
