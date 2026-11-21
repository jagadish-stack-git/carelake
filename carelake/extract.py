"""Readers that turn FHIR R4 resources into flat rows shaped like the schemas.

They are deliberately literal: every identifier a Patient carries is read, so
the raw layer is a faithful copy and the scrubber has something to prove itself
against. Dates stay as the strings FHIR gave them until the row has passed
validation.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from carelake.settings import TABLES

NPI = "http://hl7.org/fhir/sid/us-npi"
SSN = "http://hl7.org/fhir/sid/us-ssn"
X = {
    "race": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race",
    "ethnicity": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity",
    "sex_at_birth": "http://hl7.org/fhir/us/core/StructureDefinition/us-core-birthsex",
    "mother_maiden": "http://hl7.org/fhir/StructureDefinition/patient-mothersMaidenName",
    "birthplace": "http://hl7.org/fhir/StructureDefinition/patient-birthPlace",
    "geo": "http://hl7.org/fhir/StructureDefinition/geolocation",
}


def dig(obj: Any, *path: Any, default: Any = None) -> Any:
    """Walk dicts and lists; any miss returns the default."""
    cur = obj
    for p in path:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and isinstance(p, int) and -len(cur) <= p < len(cur):
            cur = cur[p]
        else:
            return default
        if cur is None:
            return default
    return cur


def target(ref: dict | None) -> str | None:
    """The id part of a reference, whichever of the three FHIR styles it uses."""
    r = dig(ref, "reference")
    if not r:
        return None
    if r.startswith("urn:uuid:"):
        return r[len("urn:uuid:") :]
    if "?identifier=" in r:
        return r.rsplit("|", 1)[-1]
    return r.rsplit("/", 1)[-1]


def is_npi(ref: dict | None) -> bool:
    return NPI in (dig(ref, "reference") or "")


def code_of(cc: dict | None) -> dict:
    return dig(cc, "coding", 0, default={}) or {}


def ext_value(res: dict, url: str) -> Any:
    for e in res.get("extension") or []:
        if e.get("url") != url:
            continue
        for sub in e.get("extension") or []:
            if sub.get("url") == "text":
                return sub.get("valueString")
        for k, v in e.items():
            if k.startswith("value"):
                return v
    return None


def ident(res: dict, type_code: str | None = None, system: str | None = None) -> str | None:
    for i in res.get("identifier") or []:
        if type_code and dig(i, "type", "coding", 0, "code") == type_code:
            return i.get("value")
        if system and i.get("system") == system:
            return i.get("value")
    return None


# ------------------------------------------------------------------ per table


def patient_row(r: dict) -> dict[str, Any]:
    names = r.get("name") or []
    official = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    maiden = next((n for n in names if n.get("use") == "maiden"), None)
    tel = {t.get("system"): t.get("value") for t in r.get("telecom") or []}
    addr = dig(r, "address", 0, default={}) or {}
    lat = lng = None
    for e in addr.get("extension") or []:
        if e.get("url") == X["geo"]:
            for sub in e.get("extension") or []:
                if sub.get("url") == "latitude":
                    lat = sub.get("valueDecimal")
                elif sub.get("url") == "longitude":
                    lng = sub.get("valueDecimal")
    born = ext_value(r, X["birthplace"]) or {}
    photo = dig(r, "photo", 0, default={}) or {}
    multiple = r.get("multipleBirthBoolean")
    if multiple is None and r.get("multipleBirthInteger") is not None:
        multiple = True
    return {
        "pid": r.get("id"),
        "mrn": ident(r, "MR"),
        "ssn": ident(r, "SS") or ident(r, system=SSN),
        "license_no": ident(r, "DL"),
        "passport_no": ident(r, "PPN"),
        "surname": official.get("family"),
        "forenames": " ".join(official.get("given") or []) or None,
        "prefix": " ".join(official.get("prefix") or []) or None,
        "maiden_surname": maiden.get("family") if maiden else None,
        "mother_maiden": ext_value(r, X["mother_maiden"]),
        "tel": tel.get("phone"),
        "fax": tel.get("fax"),
        "mail": tel.get("email"),
        "photo": photo.get("url") or ("inline" if photo.get("data") else None),
        "sex": r.get("gender"),
        "dob": r.get("birthDate"),
        "died_at": r.get("deceasedDateTime"),
        "marital": dig(r, "maritalStatus", "coding", 0, "code") or dig(r, "maritalStatus", "text"),
        "race": ext_value(r, X["race"]),
        "ethnicity": ext_value(r, X["ethnicity"]),
        "sex_at_birth": ext_value(r, X["sex_at_birth"]),
        "multiple_birth": multiple,
        "lang": dig(r, "communication", 0, "language", "coding", 0, "code"),
        "street": " ".join(addr.get("line") or []) or None,
        "town": addr.get("city"),
        "region": addr.get("state"),
        "zip": addr.get("postalCode"),
        "country": addr.get("country"),
        "lat": lat,
        "lng": lng,
        "born_town": born.get("city") if isinstance(born, dict) else None,
        "born_region": born.get("state") if isinstance(born, dict) else None,
        "narrative": dig(r, "text", "div"),
    }


def encounter_row(r: dict) -> dict[str, Any]:
    kind = code_of(dig(r, "type", 0))
    reason = code_of(dig(r, "reasonCode", 0))
    who = dig(r, "participant", 0, "individual", default={}) or {}
    org = r.get("serviceProvider") or {}
    return {
        "eid": r.get("id"),
        "pid": target(r.get("subject")),
        "pid_label": dig(r, "subject", "display"),
        "status": r.get("status"),
        "setting": dig(r, "class", "code"),
        "kind_code": kind.get("code"),
        "kind": kind.get("display"),
        "began": dig(r, "period", "start"),
        "ended": dig(r, "period", "end"),
        "reason_code": reason.get("code"),
        "reason": reason.get("display"),
        "facility_id": target(org),
        "facility": org.get("display"),
        "clinician_npi": target(who) if is_npi(who) else None,
        "clinician": who.get("display"),
        "site": dig(r, "location", 0, "location", "display"),
    }


def condition_row(r: dict) -> dict[str, Any]:
    c = code_of(r.get("code"))
    return {
        "cid": r.get("id"),
        "pid": target(r.get("subject")),
        "eid": target(r.get("encounter")),
        "clinical_status": dig(r, "clinicalStatus", "coding", 0, "code"),
        "verification": dig(r, "verificationStatus", "coding", 0, "code"),
        "category": dig(r, "category", 0, "coding", 0, "code"),
        "system": c.get("system"),
        "code": c.get("code"),
        "label": c.get("display") or dig(r, "code", "text"),
        "onset": r.get("onsetDateTime"),
        "abated": r.get("abatementDateTime"),
        "recorded": r.get("recordedDate"),
    }


def _value(o: dict) -> dict[str, Any]:
    q = o.get("valueQuantity") or {}
    cc = code_of(o.get("valueCodeableConcept"))
    return {
        "num_value": q.get("value"),
        "unit": q.get("unit") or q.get("code"),
        "text_value": o.get("valueString"),
        "coded_value": cc.get("code"),
        "coded_label": cc.get("display"),
    }


def observation_rows(r: dict) -> list[dict[str, Any]]:
    """The observation itself, then one row per component (a blood pressure
    panel has two). Component rows carry the parent id with a ``#n`` suffix."""
    c = code_of(r.get("code"))
    parts = r.get("component") or []
    common = {
        "pid": target(r.get("subject")),
        "eid": target(r.get("encounter")),
        "status": r.get("status"),
        "category": dig(r, "category", 0, "coding", 0, "code"),
        "taken_at": r.get("effectiveDateTime") or dig(r, "effectivePeriod", "start"),
        "issued_at": r.get("issued"),
    }
    rows = [
        {
            "oid": r.get("id"),
            "parent_oid": None,
            **common,
            "system": c.get("system"),
            "code": c.get("code"),
            "label": c.get("display") or dig(r, "code", "text"),
            **_value(r),
            "n_components": len(parts),
        }
    ]
    for n, part in enumerate(parts, 1):
        pc = code_of(part.get("code"))
        rows.append(
            {
                "oid": f"{r.get('id')}#{n}",
                "parent_oid": r.get("id"),
                **common,
                "system": pc.get("system"),
                "code": pc.get("code"),
                "label": pc.get("display"),
                **_value(part),
                "n_components": 0,
            }
        )
    return rows


def prescription_row(r: dict, meds: dict[str, dict]) -> dict[str, Any]:
    """medication[x] is a choice: an inline CodeableConcept for most orders,
    a reference to a Medication resource in the same bundle for the rest."""
    cc = r.get("medicationCodeableConcept")
    if not cc and r.get("medicationReference"):
        cc = dig(meds.get(target(r["medicationReference"]) or "", {}), "code")
    c = code_of(cc)
    who = r.get("requester") or {}
    return {
        "rxid": r.get("id"),
        "pid": target(r.get("subject")),
        "eid": target(r.get("encounter")),
        "status": r.get("status"),
        "intent": r.get("intent"),
        "category": dig(r, "category", 0, "coding", 0, "code"),
        "system": c.get("system"),
        "code": c.get("code"),
        "label": c.get("display") or dig(cc, "text"),
        "written_at": r.get("authoredOn"),
        "prescriber_npi": target(who) if is_npi(who) else None,
        "prescriber": who.get("display"),
        "for_cid": target(dig(r, "reasonReference", 0)),
    }


def procedure_row(r: dict) -> dict[str, Any]:
    c = code_of(r.get("code"))
    return {
        "prid": r.get("id"),
        "pid": target(r.get("subject")),
        "eid": target(r.get("encounter")),
        "status": r.get("status"),
        "system": c.get("system"),
        "code": c.get("code"),
        "label": c.get("display") or dig(r, "code", "text"),
        "began": dig(r, "performedPeriod", "start") or r.get("performedDateTime"),
        "ended": dig(r, "performedPeriod", "end"),
        "for_cid": target(dig(r, "reasonReference", 0)),
        "site": dig(r, "location", "display"),
    }


def immunization_row(r: dict) -> dict[str, Any]:
    c = code_of(r.get("vaccineCode"))
    return {
        "imid": r.get("id"),
        "pid": target(r.get("patient")),
        "eid": target(r.get("encounter")),
        "status": r.get("status"),
        "system": c.get("system"),
        "code": c.get("code"),
        "label": c.get("display") or dig(r, "vaccineCode", "text"),
        "given_at": r.get("occurrenceDateTime"),
        "site": dig(r, "location", "display"),
    }


def claim_row(r: dict) -> dict[str, Any]:
    cov = dig(r, "insurance", 0, "coverage", default={}) or {}
    org = r.get("provider") or {}
    eid = None
    for item in r.get("item") or []:
        ref = dig(item, "encounter", 0)
        if ref:
            eid = target(ref)
            break
    return {
        "clid": r.get("id"),
        "pid": target(r.get("patient")),
        "pid_label": dig(r, "patient", "display"),
        "eid": eid,
        "status": r.get("status"),
        "kind": dig(r, "type", "coding", 0, "code"),
        "use": r.get("use"),
        "period_from": dig(r, "billablePeriod", "start"),
        "period_to": dig(r, "billablePeriod", "end"),
        "created_at": r.get("created"),
        "facility_id": target(org),
        "facility": org.get("display"),
        "payer": cov.get("display") or target(cov),
        "member_no": dig(cov, "identifier", "value") or dig(r, "insurance", 0, "identifier", "value"),
        "amount": dig(r, "total", "value"),
        "currency": dig(r, "total", "currency"),
        "n_diagnoses": len(r.get("diagnosis") or []),
        "n_items": len(r.get("item") or []),
    }


# ------------------------------------------------------------------ bundles


def resources(bundle: dict) -> Iterator[dict]:
    for e in bundle.get("entry") or []:
        r = e.get("resource")
        if r and r.get("resourceType"):
            yield r


def read_bundle(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def rows_from_bundle(bundle: dict) -> tuple[dict[str, list[tuple[dict, dict]]], Counter]:
    """Rows per table, each with the resource it came from, and a tally of the
    resource types that were not read."""
    meds = {r.get("id"): r for r in resources(bundle) if r["resourceType"] == "Medication"}
    out: dict[str, list[tuple[dict, dict]]] = {t: [] for t in TABLES.values()}
    skipped: Counter = Counter()
    for r in resources(bundle):
        rt = r["resourceType"]
        table = TABLES.get(rt)
        if table is None:
            skipped[rt] += 1
            continue
        if rt == "Observation":
            rows = observation_rows(r)
        elif rt == "MedicationRequest":
            rows = [prescription_row(r, meds)]
        else:
            fn = {
                "Patient": patient_row,
                "Encounter": encounter_row,
                "Condition": condition_row,
                "Procedure": procedure_row,
                "Immunization": immunization_row,
                "Claim": claim_row,
            }[rt]
            rows = [fn(r)]
        out[table].extend((r, row) for row in rows)
    return out, skipped
