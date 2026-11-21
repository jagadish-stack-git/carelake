"""Paths, names and secrets, all overridable through CARELAKE_* variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

SYNTHEA_RELEASE = "v4.0.0"
SYNTHEA_URL = f"https://github.com/synthetichealth/synthea/releases/download/{SYNTHEA_RELEASE}/synthea-with-dependencies.jar"
SYNTHEA_SHA256 = "ed43c20ad40ba5c3bc724503a5af032715fe3c491620b766148e7c2361e6ecc1"

# FHIR resource type -> table in the lake. Anything not here is tallied and left alone.
TABLES = {
    "Patient": "patients",
    "Encounter": "encounters",
    "Condition": "conditions",
    "Observation": "observations",
    "MedicationRequest": "prescriptions",
    "Procedure": "procedures",
    "Immunization": "immunizations",
    "Claim": "claims",
}

# Three-digit ZIP prefixes that HHS lists as covering fewer than 20,000 people.
# Safe Harbor replaces them with 000 (45 CFR 164.514(b)(2)(i)(B)).
SMALL_ZIP3 = frozenset(
    [
        "036",
        "059",
        "063",
        "102",
        "203",
        "556",
        "692",
        "790",
        "821",
        "823",
        "830",
        "831",
        "878",
        "879",
        "884",
        "890",
        "893",
    ]
)


def env(name: str, default: str = "") -> str:
    value = os.environ.get(f"CARELAKE_{name}")
    return value if value else default


class Paths(NamedTuple):
    data: Path
    cache: Path
    web: Path
    dbt: Path

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def curated(self) -> Path:
        return self.data / "curated"

    @property
    def serving(self) -> Path:
        return self.data / "serving"

    @property
    def rejects(self) -> Path:
        return self.data / "raw" / "_rejects"

    @property
    def duckdb_file(self) -> Path:
        return self.data / "carelake.duckdb"

    @property
    def feeds(self) -> Path:
        return self.web / "feeds"

    @property
    def jar(self) -> Path:
        return self.cache / "synthea-with-dependencies.jar"


def paths() -> Paths:
    return Paths(
        data=Path(env("DATA_DIR", str(ROOT / "data"))),
        cache=Path(env("CACHE_DIR", str(ROOT / ".cache"))),
        web=ROOT / "web",
        dbt=ROOT / "dbt",
    )


def scrub_secret() -> str:
    """Keys the pseudonyms and the per-patient date offsets. The default is for
    laptops only; the scheduled refresh refuses to run on it."""
    return env("SCRUB_SECRET", "laptop-only-secret")


def feed_base_url() -> str:
    return env("FEED_BASE_URL", "https://jagadish-stack-git.github.io/carelake")


def sink() -> str:
    """'files' (default) or 'adls'."""
    return env("SINK", "files")


def adls() -> tuple[str, str]:
    return env("ADLS_ACCOUNT"), env("ADLS_KEY")


def java_opts() -> list[str]:
    return env("JAVA_OPTS", "-Xmx4g").split()
