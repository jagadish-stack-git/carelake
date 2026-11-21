"""Safe Harbor scrubbing, between raw and curated.

How each of the eighteen identifier classes in 45 CFR 164.514(b)(2) is handled:

  name              dropped: patient names, maiden names, mother's maiden name, display labels
  geo below state   street, town, coordinates, birthplace town dropped; ZIP kept to three
                    digits, 000 for the seventeen prefixes HHS lists as small
  date              offset per patient by up to 180 days, same offset for every date of
                    that patient; date of birth kept as the offset year; over 89 -> 90+
  phone, fax, email dropped
  ssn, mrn          dropped
  plan-id           dropped (member number on the claim)
  account, vehicle  not read from the bundle at all
  licence           driver's licence and passport dropped
  device            Device resources are not read
  url, ip           swept out of free text; photo URL dropped
  biometric, photo  dropped with the photo
  unique-id         every resource id replaced by a keyed BLAKE2b digest; the Synthea
                    narrative with its person seed dropped

The digest and the offset use the same secret. No mapping is stored anywhere.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pyarrow as pa

from carelake.schemas import TableSchema
from carelake.settings import SMALL_ZIP3

OFFSET_DAYS = 180
OLDEST_EXACT_AGE = 89
SCRUB_VERSION = 1

BRACKETS = ((0, 17, "under 18"), (18, 39, "18 to 39"), (40, 64, "40 to 64"), (65, 89, "65 to 89"))

SWEEP = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?1[-. ]?)?(?:\(\d{3}\)|\d{3})[-. ]\d{3}[-. ]\d{4}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "url": re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE),
}

EXTRA_CURATED = {"patients": [pa.field("age_bracket", pa.string()), pa.field("over_89", pa.bool_())]}


def curated_schema(s: TableSchema) -> pa.Schema:
    fields = list(s.arrow_curated()) + EXTRA_CURATED.get(s.name, [])
    return pa.schema(fields + [pa.field("_cohort", pa.string()), pa.field("_scrub_v", pa.int32())])


def bracket(age: int) -> str:
    if age > OLDEST_EXACT_AGE:
        return "90 and over"
    for lo, hi, label in BRACKETS:
        if lo <= age <= hi:
            return label
    return "unknown"


def zip3(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) < 5:
        return None
    head = digits[:3]
    return "000" if head in SMALL_ZIP3 else head


def age_on(born: date, day: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


@dataclass
class Tally:
    rows: int = 0
    dropped: set[str] = field(default_factory=set)
    hashed: int = 0
    offset: int = 0
    zip3: int = 0
    zip3_small: int = 0
    over_89: int = 0
    swept: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "dropped": sorted(self.dropped),
            "hashed": self.hashed,
            "offset": self.offset,
            "zip3": self.zip3,
            "zip3_small": self.zip3_small,
            "over_89": self.over_89,
            "swept": dict(self.swept),
        }


class Scrubber:
    def __init__(self, secret: str, as_of: date):
        if not secret:
            raise ValueError("the scrubber needs a secret")
        self._key = secret.encode()
        self.as_of = as_of

    def digest(self, value: str) -> str:
        return hashlib.blake2b(value.encode(), key=self._key, digest_size=16).hexdigest()

    def offset_days(self, pid: str) -> int:
        """Per-patient, in [-180, 180], never zero."""
        raw = hashlib.blake2b(pid.encode(), key=self._key, digest_size=8, person=b"offset").digest()
        n = int.from_bytes(raw, "big") % (2 * OFFSET_DAYS)
        return n - OFFSET_DAYS if n < OFFSET_DAYS else n - OFFSET_DAYS + 1

    def shift(self, when: datetime | date | None, pid: str):
        return None if when is None else when + timedelta(days=self.offset_days(pid))

    @staticmethod
    def sweep(text: str | None, tally: Tally | None = None) -> str | None:
        if not text:
            return text
        for name, pat in SWEEP.items():
            text, n = pat.subn("[redacted]", text)
            if n and tally is not None:
                tally.swept[name] += n
        return text

    def row(self, s: TableSchema, row: dict[str, Any], tally: Tally | None = None) -> dict[str, Any]:
        tally = tally if tally is not None else Tally()
        tally.rows += 1
        pid = row.get("pid")
        if not pid:
            raise ValueError(f"{s.name}: a row without pid cannot be scrubbed")
        out: dict[str, Any] = {}
        for col in s.columns:
            action = s.scrub(col)
            value = row.get(col)
            if action == "drop":
                tally.dropped.add(col)
                continue
            if action == "dob_year":
                self._dob(value, pid, out, tally)
                continue
            if value is None:
                out[col] = None
            elif action == "keep":
                out[col] = self.sweep(value, tally) if s.free_text(col) and isinstance(value, str) else value
            elif action == "hash":
                out[col] = self.digest(str(value))
                tally.hashed += 1
            elif action == "offset":
                out[col] = self.shift(value, pid)
                tally.offset += 1
            elif action == "zip3":
                z = zip3(value)
                out[col] = z
                tally.zip3 += 1
                tally.zip3_small += z == "000"
        out["_cohort"] = row.get("_cohort")
        out["_scrub_v"] = SCRUB_VERSION
        return out

    def _dob(self, born: date | None, pid: str, out: dict[str, Any], tally: Tally) -> None:
        if born is None:
            out.update(birth_year=None, age_bracket=None, over_89=None)
            return
        age = age_on(born, self.as_of)
        old = age > OLDEST_EXACT_AGE
        out["birth_year"] = None if old else self.shift(born, pid).year
        out["age_bracket"] = bracket(age)
        out["over_89"] = old
        tally.offset += 1
        tally.over_89 += old
