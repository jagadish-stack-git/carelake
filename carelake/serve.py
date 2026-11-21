"""The serving layer: dbt on DuckDB over the curated parquet, then every mart
copied out as parquet so the lake can be read without dbt."""

from __future__ import annotations

import json
import os

import duckdb

from carelake.settings import Paths

MARTS = [
    "patient_dim",
    "calendar_dim",
    "condition_dim",
    "drug_dim",
    "facility_dim",
    "payer_dim",
    "encounter_fact",
    "diagnosis_fact",
    "prescription_fact",
    "result_fact",
    "procedure_fact",
    "vaccination_fact",
    "chronic_pairs",
    "diabetes_care_gaps",
    "reject_log",
    "scrub_ledger",
    "reidentification_risk",
]


def _env_for_dbt(paths: Paths) -> dict[str, str]:
    return {
        "CARELAKE_DUCKDB": paths.duckdb_file.as_posix(),
        "CARELAKE_CURATED": paths.curated.as_posix(),
        "CARELAKE_RAW": paths.raw.as_posix(),
    }


def run_dbt(paths: Paths, say=print) -> dict:
    from dbt.adapters.factory import reset_adapters
    from dbt.cli.main import dbtRunner

    paths.duckdb_file.parent.mkdir(parents=True, exist_ok=True)
    previous = {k: os.environ.get(k) for k in _env_for_dbt(paths)}
    os.environ.update(_env_for_dbt(paths))
    try:
        res = dbtRunner().invoke(
            ["build", "--project-dir", paths.dbt.as_posix(), "--profiles-dir", paths.dbt.as_posix()]
        )
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    reset_adapters()  # dbt holds the DuckDB file open otherwise
    if res.exception:
        raise res.exception
    out = {
        "ok": bool(res.success),
        "models": 0,
        "tests": 0,
        "tests_ok": 0,
        "tests_warn": 0,
        "failed": [],
        "warned": [],
    }
    for r in getattr(res.result, "results", None) or []:
        kind, status = r.node.resource_type, str(r.status)
        if kind == "model":
            out["models"] += 1
        elif kind == "test":
            out["tests"] += 1
            if status == "pass":
                out["tests_ok"] += 1
            elif status == "warn":
                out["tests_warn"] += 1
                out["warned"].append(r.node.name)
        if status in ("error", "fail"):
            out["failed"].append(f"{kind} {r.node.name}: {r.message}")
    if not res.success:
        raise RuntimeError("dbt build failed: " + "; ".join(out["failed"][:5]))
    say(
        f"dbt: {out['models']} models, {out['tests_ok']}/{out['tests']} tests ok"
        + (f", {out['tests_warn']} warned" if out["tests_warn"] else "")
    )
    return out


def export_marts(paths: Paths, say=print) -> dict[str, int]:
    paths.serving.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, int] = {}
    with duckdb.connect(str(paths.duckdb_file)) as con:
        for m in MARTS:
            target = paths.serving / f"{m}.parquet"
            con.execute(
                f"copy (select * from marts.{m}) to '{target.as_posix()}' (format parquet, compression zstd)"
            )
            sizes[m] = con.execute(f"select count(*) from marts.{m}").fetchone()[0]
    (paths.serving / "_marts.json").write_text(json.dumps(sizes, indent=1), encoding="utf-8")
    say(f"serving: {len(sizes)} marts written to {paths.serving}")
    return sizes


def lake_bytes(paths: Paths) -> int:
    return paths.duckdb_file.stat().st_size if paths.duckdb_file.exists() else 0
