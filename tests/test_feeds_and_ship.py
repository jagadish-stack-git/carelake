from __future__ import annotations

from datetime import date
from pathlib import Path

from carelake import adls
from carelake.feeds import history_point, monday, upsert
from carelake.generate import Cohort, weekly_cohort
from carelake.settings import Paths


def test_monday():
    assert monday(date(2026, 11, 21)) == date(2026, 11, 16) == monday(date(2026, 11, 16))


def test_upsert_keeps_one_point_per_week_sorted():
    h = [{"week": "2026-11-09", "patients": 1}, {"week": "2026-11-16", "patients": 2}]
    h = upsert(h, {"week": "2026-11-16", "patients": 3})
    h = upsert(h, {"week": "2026-11-02", "patients": 0})
    assert [p["week"] for p in h] == ["2026-11-02", "2026-11-09", "2026-11-16"] and h[-1]["patients"] == 3
    assert upsert(["junk", {"nope": 1}], {"week": "2026-11-16"}) == [{"week": "2026-11-16"}]


def test_history_point_shape():
    s = {
        "built_at": "2026-11-21T00:00:00+00:00",
        "counts": {"patients": 2, "encounters": 9, "diagnoses": 4, "results": 30, "rejects": 0},
        "care_gaps": {"statin_share": 0.25, "a1c_share": None},
        "scrub": {"risk": {"smallest_group": 1, "unique_share": 0.5}},
        "pairs": [{"bucket_a": "obesity", "bucket_b": "anemia"}],
        "dbt": {"tests": 80, "tests_ok": 80},
    }
    p = history_point(s, date(2026, 11, 21), ["t"])
    assert p["week"] == "2026-11-16" and p["top_pair"] == "obesity & anemia" and p["tests"] == 80


def test_weekly_cohort_is_a_pure_function_of_the_week():
    a, b = weekly_cohort(date(2026, 11, 16), 400), weekly_cohort(date(2026, 11, 22), 400)
    assert a == b and a.label == "w202647" and a.as_of == date(2026, 11, 16)
    assert Cohort("il-7", 7, 1500, date(2026, 11, 21)).state == "Illinois"


class Fake:
    def __init__(self):
        self.sent: list[tuple[str, str, Path]] = []

    def send(self, fs, remote, local):
        self.sent.append((fs, remote, local))


def _touch(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0")


def test_ship_is_dormant_for_files_sink(lake):
    f = Fake()
    assert adls.ship(lake, "files", "", "", shipper=f, say=lambda m: None) == 0 and f.sent == []


def test_ship_covers_all_layers(lake):
    _touch(lake.raw / "patients" / "t.parquet")
    _touch(lake.rejects / "t.parquet")
    _touch(lake.curated / "patients" / "t.parquet")
    _touch(lake.serving / "patient_dim.parquet")
    _touch(lake.feeds / "status.json")
    f = Fake()
    n = adls.ship(lake, "adls", "acct", "", shipper=f, say=lambda m: None)
    got = {(fs, r) for fs, r, _ in f.sent}
    assert n == 5
    assert {
        ("raw", "_rejects/t.parquet"),
        ("curated", "patients/t.parquet"),
        ("serving", "patient_dim.parquet"),
        ("feeds", "status.json"),
    } <= got


def test_ship_can_be_limited(lake):
    _touch(lake.raw / "patients" / "t.parquet")
    _touch(lake.serving / "calendar_dim.parquet")
    f = Fake()
    adls.ship(lake, "adls", "acct", "", shipper=f, layers=["serving"], say=lambda m: None)
    assert {fs for fs, _, _ in f.sent} == {"serving"}


def test_paths_layout(lake: Paths):
    assert lake.rejects == lake.raw / "_rejects" and lake.feeds == lake.web / "feeds"
