"""Sample bundles through raw and curated in a throwaway lake, including the
check that nothing identifying from the bundles survives into curated."""

from __future__ import annotations

import json
import re

import duckdb
import pyarrow.parquet as pq

from carelake import extract
from carelake.curate import curate_cohort
from carelake.land import land_cohort


def identifying_values(bundles: list[dict]) -> set[str]:
    vals: set[str] = set()
    for b in bundles:
        for r in extract.resources(b):
            vals.add(r["id"])
            if r["resourceType"] != "Patient":
                continue
            for n in r.get("name", []):
                vals.update(n.get("given", []))
                vals.add(n.get("family", ""))
            vals.update(i.get("value", "") for i in r.get("identifier", []))
            vals.update(t.get("value", "") for t in r.get("telecom", []))
            for a in r.get("address", []):
                vals.update(a.get("line", []))
                vals.add(a.get("city", ""))
                vals.add(a.get("postalCode", ""))
                for e in a.get("extension", []):
                    for sub in e.get("extension", []):
                        if "valueDecimal" in sub:
                            vals.add(str(sub["valueDecimal"]))
            vals.add(r.get("birthDate", ""))
            m = re.search(r"Person seed:\s*(-?\d+)", (r.get("text") or {}).get("div", ""))
            if m:
                vals.add(m.group(1))
    return {v for v in vals if v and len(v) >= 4}


def quiet(_msg: str) -> None:
    pass


def test_landing_writes_rows_manifest_and_rejects(lake, samples):
    rep = land_cohort(lake, "t", quiet)
    assert rep["bundles"] == len(samples) and rep["rows"]["patients"] == len(samples)
    assert rep["rows"]["encounters"] > 0 and rep["rows"]["claims"] > 0
    assert (lake.rejects / "t.parquet").exists()
    assert "DiagnosticReport" in rep["not_read"]
    assert json.loads((lake.raw / "_manifest" / "t.json").read_text())["schema_versions"]["patients"] == 1


def test_landing_twice_gives_the_same_result(lake):
    a = land_cohort(lake, "t", quiet)
    b = land_cohort(lake, "t", quiet)
    assert a["rows"] == b["rows"]
    assert pq.read_metadata(lake.raw / "encounters" / "t.parquet").num_rows == a["rows"]["encounters"]


def test_bad_rows_are_rejected_with_problems_not_lost(lake, samples):
    bad = json.loads(json.dumps(samples[0]))
    enc = next(r for r in extract.resources(bad) if r["resourceType"] == "Encounter")
    enc["period"] = {"start": "2020-05-05T00:00:00Z", "end": "2020-05-04T00:00:00Z"}
    cond = next(r for r in extract.resources(bad) if r["resourceType"] == "Condition")
    cond.pop("code")
    (lake.raw / "t" / "fhir" / "zz_broken.json").write_text(json.dumps(bad), encoding="utf-8")

    rep = land_cohort(lake, "t", quiet)
    rows = duckdb.sql(
        f"select table_name, problems from '{(lake.rejects / 't.parquet').as_posix()}'"
    ).fetchall()
    by_table: dict[str, str] = {}
    for t, p in rows:
        by_table[t] = by_table.get(t, "") + " ; " + p
    assert "ended: earlier than began" in by_table["encounters"]
    assert "system: missing" in by_table["conditions"] and "code: missing" in by_table["conditions"]
    assert "pid: repeated in cohort" in by_table["patients"]
    assert rep["rejected_total"] >= 3
    raw = duckdb.sql(
        f"select resource from '{(lake.rejects / 't.parquet').as_posix()}' where table_name = 'conditions'"
    ).fetchone()[0]
    assert json.loads(raw)["resourceType"] == "Condition"


def test_nothing_identifying_reaches_curated(lake, samples, schemas):
    land_cohort(lake, "t", quiet)
    curate_cohort(lake, "t", "lake-test-secret", quiet)
    needles = identifying_values(samples)
    assert len(needles) > 20
    pieces = []
    for table, s in schemas.items():
        tbl = pq.read_table(lake.curated / table / "t.parquet")
        for c in s.columns:
            if s.scrub(c) == "drop":
                assert c not in tbl.schema.names, (table, c)
        if "facility_id" in tbl.schema.names:  # a facility is an organisation, kept as Synthea's UUID
            tbl = tbl.drop_columns(["facility_id"])
        pieces.append(json.dumps(tbl.to_pylist(), default=str))
    text = "\n".join(pieces)
    assert [n for n in needles if n in text] == []
    assert not re.search(r"\b\d{3}-\d{2}-\d{4}\b", text)
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)
    assert "@" not in text


def test_tally_is_written(lake):
    land_cohort(lake, "t", quiet)
    rep = curate_cohort(lake, "t", "lake-test-secret", quiet)
    tally = pq.read_table(lake.curated / "_tally" / "t.parquet").to_pylist()
    assert {t["table_name"] for t in tally} == set(rep["tables"])
    p = next(t for t in tally if t["table_name"] == "patients")
    assert "ssn" in p["dropped"] and p["hashed"] == p["rows"]
