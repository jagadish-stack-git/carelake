import pytest

from carelake.schemas import PHI_CLASSES, parse_when
from carelake.settings import TABLES


def test_one_schema_per_table(schemas):
    assert set(schemas) == set(TABLES.values())
    for s in schemas.values():
        assert s.resource in TABLES and s.key in s.columns


def test_phi_columns_never_keep(schemas):
    bad = [(s.name, c) for s in schemas.values() for c in s.columns if s.phi(c) and s.scrub(c) == "keep"]
    assert bad == []


def test_non_phi_columns_only_keep_or_drop(schemas):
    for s in schemas.values():
        for c in s.columns:
            if not s.phi(c):
                assert s.scrub(c) in ("keep", "drop"), (s.name, c)


def test_pid_is_hashed_everywhere(schemas):
    for s in schemas.values():
        assert s.scrub("pid") == "hash", s.name


def test_eighteen_classes_declared():
    assert len(PHI_CLASSES) == 18


def test_codes_and_systems_are_not_free_text(schemas):
    for s in schemas.values():
        for c in ("system", "code"):
            if c in s.columns:
                assert not s.free_text(c), (s.name, c)


def test_accepts_a_good_row(schemas):
    row = {
        "cid": "c",
        "pid": "p",
        "system": "http://snomed.info/sct",
        "code": "44054006",
        "onset": "2020-01-01T00:00:00Z",
    }
    assert schemas["conditions"].problems(row) == []


def test_reports_missing_required_and_bad_enum(schemas):
    out = schemas["encounters"].problems({"eid": "e", "pid": "p", "status": "finished", "setting": "NOPE"})
    assert "began: missing" in out
    assert any(p.startswith("setting:") for p in out)


def test_rules_catch_future_and_reversed_periods(schemas):
    from datetime import date

    out = schemas["encounters"].problems(
        {
            "eid": "e",
            "pid": "p",
            "status": "finished",
            "setting": "AMB",
            "began": "2030-01-02T00:00:00Z",
            "ended": "2030-01-01T00:00:00Z",
        },
        today=date(2026, 11, 21),
    )
    assert "began: later than today" in out
    assert "ended: earlier than began" in out


def test_phi_values_are_not_echoed(schemas):
    out = schemas["patients"].problems({"pid": "p", "sex": "male", "dob": "1990-01-01", "ssn": "12-345-6789"})
    assert out and all("12-345" not in p for p in out)
    assert "ssn: fails pattern" in out


def test_unknown_columns_are_rejected(schemas):
    out = schemas["claims"].problems(
        {
            "clid": "c",
            "pid": "p",
            "status": "active",
            "kind": "oral",
            "period_from": "2020-01-01",
            "payer": "x",
            "extra": 1,
        }
    )
    assert any("extra" in p for p in out)


def test_panel_parents_need_no_value(schemas):
    base = {
        "oid": "o",
        "pid": "p",
        "status": "final",
        "system": "http://loinc.org",
        "code": "85354-9",
        "taken_at": "2020-01-01",
    }
    assert schemas["observations"].problems({**base, "n_components": 2}) == []
    assert schemas["observations"].problems({**base, "n_components": 0}) == [
        "no value in any of num_value, text_value, coded_value"
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2000-08-31T07:59:28-05:00", "2000-08-31T12:59:28+00:00"),
        ("2019", "2019-01-01T00:00:00+00:00"),
        ("2019-03", "2019-03-01T00:00:00+00:00"),
        ("2019-03-04T10:00:00Z", "2019-03-04T10:00:00+00:00"),
    ],
)
def test_parse_when(text, expected):
    assert parse_when(text).isoformat() == expected


def test_curated_arrow_schema_drops_and_renames(schemas):
    names = schemas["patients"].arrow_curated().names
    assert "ssn" not in names and "surname" not in names and "dob" not in names
    assert "birth_year" in names and "zip" in names
