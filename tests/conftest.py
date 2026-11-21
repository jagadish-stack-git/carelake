from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from carelake.schemas import load_all
from carelake.settings import Paths

SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture(scope="session")
def schemas():
    return load_all()


@pytest.fixture(scope="session")
def samples() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES.glob("sample_*.json"))]


@pytest.fixture
def lake(tmp_path: Path) -> Paths:
    """A throwaway lake whose cohort 't' holds the sample bundles."""
    data = tmp_path / "data"
    fhir = data / "raw" / "t" / "fhir"
    fhir.mkdir(parents=True)
    for p in sorted(SAMPLES.glob("sample_*.json")):
        shutil.copy(p, fhir / p.name)
    (data / "raw" / "t" / "manifest.json").write_text(
        json.dumps({"label": "t", "as_of": "2026-11-21"}), encoding="utf-8"
    )
    web = tmp_path / "web"
    web.mkdir()
    return Paths(
        data=data, cache=tmp_path / "cache", web=web, dbt=Path(__file__).resolve().parents[1] / "dbt"
    )
