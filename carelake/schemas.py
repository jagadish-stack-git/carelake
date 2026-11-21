"""The eight table schemas under schemas/, as JSON Schema 2020-12 with three
vendor keywords: ``x-phi`` (Safe Harbor class), ``x-scrub`` (what the scrubber
does) and ``x-free-text`` (sweep the value for identifier-shaped strings).

One file is the single description of a table: it validates rows at the door,
yields the Arrow schema for the raw and curated parquet, and tells the scrubber
what to do with each column.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
from jsonschema import Draft202012Validator

from carelake.settings import ROOT

SCHEMA_DIR = ROOT / "schemas"

PHI_CLASSES = (
    "name",
    "geo",
    "date",
    "phone",
    "fax",
    "email",
    "ssn",
    "mrn",
    "plan-id",
    "account",
    "licence",
    "vehicle",
    "device",
    "url",
    "ip",
    "biometric",
    "photo",
    "unique-id",
)
SCRUB_ACTIONS = ("keep", "drop", "hash", "offset", "zip3", "dob_year")


@dataclass(frozen=True)
class TableSchema:
    name: str
    resource: str
    key: str
    version: int
    raw: dict[str, Any]
    _validator: Draft202012Validator

    # -- column metadata ---------------------------------------------------
    @property
    def columns(self) -> list[str]:
        return list(self.raw["properties"])

    def prop(self, column: str) -> dict[str, Any]:
        return self.raw["properties"][column]

    def phi(self, column: str) -> str | None:
        return self.prop(column).get("x-phi")

    def scrub(self, column: str) -> str:
        return self.prop(column).get("x-scrub", "keep")

    def free_text(self, column: str) -> bool:
        return bool(self.prop(column).get("x-free-text"))

    def fmt(self, column: str) -> str | None:
        return self.prop(column).get("format")

    def base_type(self, column: str) -> str:
        t = self.prop(column)["type"]
        types = [x for x in (t if isinstance(t, list) else [t]) if x != "null"]
        return types[0]

    def curated_columns(self) -> list[str]:
        out = []
        for c in self.columns:
            action = self.scrub(c)
            if action == "drop":
                continue
            out.append("birth_year" if action == "dob_year" else c)
        return out

    # -- arrow ---------------------------------------------------------------
    def _arrow_type(self, column: str) -> pa.DataType:
        t, f = self.base_type(column), self.fmt(column)
        if f == "date":
            return pa.date32()
        if f == "date-time":
            return pa.timestamp("us", tz="UTC")
        return {"string": pa.string(), "integer": pa.int64(), "number": pa.float64(), "boolean": pa.bool_()}[
            t
        ]

    def arrow_raw(self) -> pa.Schema:
        return pa.schema([pa.field(c, self._arrow_type(c)) for c in self.columns])

    def arrow_curated(self) -> pa.Schema:
        fields = []
        for c in self.columns:
            action = self.scrub(c)
            if action == "drop":
                continue
            if action == "dob_year":
                fields.append(pa.field("birth_year", pa.int32()))
            else:
                fields.append(pa.field(c, self._arrow_type(c)))
        return pa.schema(fields)

    # -- validation ----------------------------------------------------------
    def problems(self, row: dict[str, Any], today: date | None = None) -> list[str]:
        """Everything wrong with the row, as short strings. Empty means accepted.
        Values of PHI columns are never echoed."""
        today = today or datetime.now(UTC).date()
        out: list[str] = []
        # a None in a required column counts as missing, not as a present null
        present = {k: v for k, v in row.items() if v is not None}
        for err in sorted(self._validator.iter_errors(present), key=lambda e: list(e.path)):
            col = str(err.path[0]) if err.path else None
            if col and self.phi(col):
                out.append(f"{col}: fails {err.validator}")
            elif err.validator == "required":
                out.append(err.message.split("'")[1] + ": missing")
            else:
                out.append(f"{col or '$'}: {err.message}")
        for rule in self.raw.get("x-rules", []):
            msg = _rule(rule, row, today)
            if msg:
                out.append(msg)
        return out


def _when(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=UTC)
    try:
        return parse_when(str(v))
    except ValueError:
        return None


def parse_when(text: str) -> datetime:
    """FHIR date / dateTime / instant to an aware UTC datetime. 'YYYY' and
    'YYYY-MM' mean the first instant of the period."""
    s = text.strip()
    if re.fullmatch(r"\d{4}", s):
        s += "-01-01"
    elif re.fullmatch(r"\d{4}-\d{2}", s):
        s += "-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return datetime.fromisoformat(s).replace(tzinfo=UTC)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def _rule(rule: dict[str, Any], row: dict[str, Any], today: date) -> str | None:
    kind = rule["check"]
    if kind == "past":
        v = _when(row.get(rule["field"]))
        if v is not None and v.date() > today:
            return f"{rule['field']}: later than today"
        return None
    if kind == "ordered":
        a, b = _when(row.get(rule["earlier"])), _when(row.get(rule["later"]))
        if a is not None and b is not None and b < a:
            return f"{rule['later']}: earlier than {rule['earlier']}"
        return None
    if kind == "any_of":
        gate = rule.get("unless_positive")
        if gate and (row.get(gate) or 0) > 0:
            return None
        if all(row.get(f) is None for f in rule["fields"]):
            return "no value in any of " + ", ".join(rule["fields"])
        return None
    raise ValueError(f"unknown check {kind}")


def load_schema(path: Path) -> TableSchema:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for col, spec in raw["properties"].items():
        if "x-phi" in spec and spec["x-phi"] not in PHI_CLASSES:
            raise ValueError(f"{path.name}: {col} has unknown x-phi {spec['x-phi']}")
        if spec.get("x-scrub", "keep") not in SCRUB_ACTIONS:
            raise ValueError(f"{path.name}: {col} has unknown x-scrub {spec['x-scrub']}")
    Draft202012Validator.check_schema(raw)
    return TableSchema(
        name=raw["title"],
        resource=raw["x-resource"],
        key=raw["x-key"],
        version=int(raw["x-version"]),
        raw=raw,
        _validator=Draft202012Validator(raw),
    )


def load_all(directory: Path = SCHEMA_DIR) -> dict[str, TableSchema]:
    return {s.name: s for s in (load_schema(p) for p in sorted(directory.glob("*.schema.json")))}


def coerce(schema: TableSchema, row: dict[str, Any]) -> dict[str, Any]:
    """Turn the validated string dates into date / datetime objects for Arrow."""
    out = dict(row)
    for c in schema.columns:
        v = out.get(c)
        if v is None:
            continue
        f = schema.fmt(c)
        if f == "date":
            out[c] = parse_when(v).date()
        elif f == "date-time":
            out[c] = parse_when(v)
    return out
