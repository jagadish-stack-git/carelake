from carelake import extract


def test_target_handles_all_reference_styles():
    assert extract.target({"reference": "urn:uuid:abc"}) == "abc"
    assert extract.target({"reference": "Patient/abc"}) == "abc"
    assert (
        extract.target({"reference": "Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|12345"})
        == "12345"
    )
    assert extract.target(None) is None


def test_dig_never_raises():
    assert extract.dig({"a": [{"b": 1}]}, "a", 0, "b") == 1
    assert extract.dig({"a": [{"b": 1}]}, "a", 3, "b") is None
    assert extract.dig(None, "x", default=0) == 0


def test_samples_fill_every_table_and_pass_validation(samples, schemas):
    filled = set()
    for b in samples:
        per_table, skipped = extract.rows_from_bundle(b)
        for table, pairs in per_table.items():
            for _, row in pairs:
                assert schemas[table].problems(row) == [], (table, row)
                filled.add(table)
        assert skipped["DiagnosticReport"] > 0
    assert {"patients", "encounters", "conditions", "claims", "observations"} <= filled


def test_patient_reader_picks_up_all_identifiers(samples):
    patient = next(r for r in extract.resources(samples[0]) if r["resourceType"] == "Patient")
    row = extract.patient_row(patient)
    for col in (
        "ssn",
        "mrn",
        "surname",
        "forenames",
        "tel",
        "street",
        "town",
        "zip",
        "lat",
        "lng",
        "mother_maiden",
        "dob",
        "narrative",
    ):
        assert row[col] is not None, col
    assert "Person seed" in row["narrative"]


def test_blood_pressure_becomes_three_rows():
    bp = {
        "resourceType": "Observation",
        "id": "bp",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": "85354-9", "display": "BP panel"}]},
        "subject": {"reference": "urn:uuid:p"},
        "effectiveDateTime": "2020-01-01T00:00:00Z",
        "component": [
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4"}]},
                "valueQuantity": {"value": 78, "unit": "mm[Hg]"},
            },
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
                "valueQuantity": {"value": 118, "unit": "mm[Hg]"},
            },
        ],
    }
    rows = extract.observation_rows(bp)
    assert [r["oid"] for r in rows] == ["bp", "bp#1", "bp#2"]
    assert rows[0]["n_components"] == 2 and rows[0]["num_value"] is None
    assert rows[2]["parent_oid"] == "bp" and rows[2]["num_value"] == 118


def test_medication_reference_resolves_inside_the_bundle():
    bundle = {
        "entry": [
            {
                "resource": {
                    "resourceType": "Medication",
                    "id": "m",
                    "code": {"coding": [{"system": "rx", "code": "77", "display": "Mix"}]},
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationRequest",
                    "id": "r",
                    "status": "active",
                    "intent": "order",
                    "subject": {"reference": "urn:uuid:p"},
                    "authoredOn": "2020-01-01",
                    "medicationReference": {"reference": "urn:uuid:m"},
                }
            },
        ]
    }
    per_table, skipped = extract.rows_from_bundle(bundle)
    ((_, row),) = per_table["prescriptions"]
    assert (row["code"], row["label"]) == ("77", "Mix") and skipped["Medication"] == 1


def test_claims_carry_payer_and_encounter(samples):
    rows = [
        extract.claim_row(r) for b in samples for r in extract.resources(b) if r["resourceType"] == "Claim"
    ]
    assert rows and all(r["payer"] for r in rows) and any(r["eid"] for r in rows)
