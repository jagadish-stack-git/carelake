# carelake

**Live: https://jagadish-stack-git.github.io/carelake/**

A FHIR R4 lakehouse that forgets who you are before it remembers anything
else. Bundles come in, JSON Schema decides what gets through the door,
everything that identifies a person is scrubbed to HIPAA Safe Harbor before the
curated layer exists, and dbt turns the rest into a Kimball star on DuckDB that
can answer a clinical question. With one switch the whole lake ships to Azure
Data Lake Storage Gen2.

The question it answers: **which chronic conditions share patients more often
than chance, and how often does a new type 2 diabetic get a statin and an
HbA1c on time, by age bracket and payer class?**

Nobody in it exists. Every patient is [Synthea](https://github.com/synthetichealth/synthea)
output from a fixed seed. That is the only way to show PHI handling in public,
and it means the scrubbing is demonstrated, not certified. I do not use the
word "compliant" anywhere on purpose.

## The shape of it

```
Synthea, seeded ──► raw/<cohort>/fhir/*.json              identified bundles, ~2 MB a patient
                        │
                        ▼  carelake land        schemas/*.schema.json at the door
                    raw/<table>/<cohort>.parquet          accepted rows, still identified
                    raw/_rejects/<cohort>.parquet         rows that failed, with every problem + the resource
                        │
                        ▼  carelake scrub       18 Safe Harbor classes, keyed BLAKE2b, per-patient date offset
                    curated/<table>/<cohort>.parquet      pseudonymous; dropped columns do not exist here
                    curated/_tally/<cohort>.parquet       what the scrubber did, per table
                        │
                        ▼  carelake serve       dbt build on DuckDB
                    core.*_v  ─►  marts.*_dim, *_fact, chronic_pairs, diabetes_care_gaps, reject_log,
                                  scrub_ledger, reidentification_risk      serving/<mart>.parquet
                        │
                        ▼  carelake feeds       status.json + history.json  ─►  web/  ─►  GitHub Pages
                        ▼  carelake ship        CARELAKE_SINK=adls  ─►  ADLS Gen2: raw / curated / serving / feeds
```

| Piece | Built with | Notes |
| --- | --- | --- |
| Source | Synthea v4.0.0, Illinois, population seed 7, clinician seed 7, as-of 2026-11-21 | 1,500 living and 205 deceased patients; the jar's SHA-256 is pinned |
| Door | JSON Schema 2020-12, one file per table | `x-phi` names the Safe Harbor class, `x-scrub` what happens to it, `x-free-text` whether the value is swept; cross-field rules in `x-rules` |
| Raw | Python, pyarrow, zstd parquet | Patient, Encounter, Condition, Observation, MedicationRequest, Procedure, Immunization, Claim; the other twelve resource types are counted, not read |
| Scrub | keyed BLAKE2b digests, per-patient offsets of up to 180 days, ZIP3 with the HHS small-area list, 90+ cap, regex sweep | one tally row per table per cohort |
| Serving | dbt-duckdb 1.12 | 10 core views, 6 dimensions, 6 facts, 2 analytic marts, 3 reports; 90 tests |
| Page and feeds | plain HTML, CSS, JS on GitHub Pages | `feeds/status.json` and `feeds/history.json`, served with an open CORS header |
| Azure | Bicep | ADLS Gen2 account, filesystem per layer, raw tiers to cool at 60 days, $1 budget alert; Synapse serverless views over `serving/` |
| Checks | GitHub Actions | ruff, 74 unit tests, then a 35-patient cohort through every stage with dbt's 90 tests and a feed check |

## Running it

Python 3.11 or newer and Java 17 on the PATH. The first run fetches the 200 MB
Synthea jar. The default cohort takes about 15 minutes on a laptop and 6 GB of
disk; pass a smaller size to look around.

```powershell
.\run.ps1 -Size 150
```

```bash
./run.sh 150
```

Both call `python -m carelake all`, which is the six stages in order:
`generate`, `land`, `scrub`, `serve`, `feeds`, `ship`. Each is also its own
subcommand. Then:

```powershell
.\.venv\Scripts\python -m http.server -d web 8080
```

Tests need no Java and no data:

```powershell
.\.venv\Scripts\python -m pytest
```

## What the first full run produced

Cohort `il-7` on a laptop, 2026-11-21.

| Stage | Outcome |
| --- | --- |
| Synthea | 1,705 bundles (1,500 living, 205 deceased), 5.5 GB of JSON |
| raw | 1,782,942 rows across eight tables; **0 rejected**; 544,000 resources of twelve other types counted and left alone |
| curated | 5.72 million ids hashed, 3.68 million dates offset, 19 columns dropped from patients alone, 0 free-text redactions needed |
| serving | 27 dbt models, 90 tests, 0 failures; the DuckDB file is 160 MB |

### Conditions that share patients

Of 1,705 patients, how many carry both, and the lift against independence:

| Pair | Patients | Lift |
| --- | --- | --- |
| anemia + obesity | 400 | 1.50 |
| high blood pressure + obesity | 264 | 1.61 |
| chronic pain + obesity | 234 | 1.28 |
| heart disease + obesity | 208 | 1.74 |

Obesity is in every top pair because Synthea assigns it to a large share of
adults, so almost everything co-occurs with it. The signal sits lower in the
table: high blood pressure with metabolic syndrome runs at 3.7 times chance on
172 patients, which is the definition of metabolic syndrome agreeing with
itself, and the allergy triad of asthma, allergic rhinitis and atopic
dermatitis runs at 10 to 14 times chance on small counts, which is the atopic
march Synthea's modules encode. The page shows the full list from the feed.

### Care gaps after a type 2 diabetes diagnosis

120 patients have a first type 2 diabetes diagnosis. Dates are offset per
patient but every date of one patient moves together, so the windows are exact.

| Measure | Denominator | Met |
| --- | --- | --- |
| Statin ordered within 365 days | 86 patients aged 40 to 75 at diagnosis | 5 (5.8%) |
| HbA1c resulted within 90 days | 120 | 47 (39.2%) |

| Payer class | Diabetics | Statin | HbA1c |
| --- | --- | --- | --- |
| commercial | 57 | 4.3% | 45.6% |
| government (Medicare, Medicaid, dual) | 43 | 11.1% | 39.5% |
| uninsured | 20 | 0.0% | 20.0% |

Uninsured patients get the HbA1c less than half as often as insured ones. That
gradient is planted by Synthea's payer model, which lets uninsured patients
skip care, and it is a good check that the measure is wired right. The statin
share is low for everyone because Synthea's diabetes module manages glucose and
does not model lipid therapy the way guidelines do. On real claims I would
expect the opposite magnitude.

### What scrubbing leaves behind

Safe Harbor removes direct identifiers. It does not make a record anonymous.
`marts.reidentification_risk` groups the curated patients on the six
quasi-identifiers that survive (age bracket, sex, race, ethnicity, region,
ZIP3):

| | |
| --- | --- |
| Groups | 473 |
| Smallest group | 1 |
| Patients unique on all six | 179 (10.5%) |
| In groups smaller than 5 | 40.6% |
| In groups smaller than 11 | 68.3% |

A release that wanted k of 5 would have to give up ZIP3 or collapse race and
ethnicity. The dbt test `k_floor` warns when more than half the patients sit in
groups under 5.

### Three things the data taught me

**A third of prescriptions carry their drug by reference.**
`MedicationRequest.medication[x]` is a choice type. Synthea writes the code
inline for ordinary orders and as a reference to a `Medication` resource in the
same bundle for administered drugs. 24,846 of 71,285 prescriptions (35%) use
the reference. A reader that only looks at `medicationCodeableConcept` rejects
all of them for having no code; `extract.prescription_row` resolves the
reference inside the bundle and the schema still rejects an order with neither.

**A required field that is present but null is not missing to JSON Schema.**
`required` checks that the key exists. My readers always emit every key, so a
Condition with no code arrived as `"code": null` and sailed through. The
validator now strips nulls before validation, and the test that corrupts a
sample bundle is what caught it.

**Synthea leaks identity where a FHIR parser does not look.** The output file
name is `First_Last_uuid.json`, so the raw layer records only the file's
SHA-256. And `Patient.text.div` holds `Person seed: -1122334455667788990`, a
number unique to that patient; the narrative is dropped as class 18.

## Scrubbing, class by class

`schemas/*.schema.json` tag every column with `x-phi` and `x-scrub`.
`tests/test_scrub_safe_harbor.py` runs one parametrised case per class against
a patient built to carry all eighteen, and `tests/test_lake.py` proves that no
identifying value from the sample bundles (names, numbers, addresses, birth
date, coordinates, UUIDs, the Synthea seed) appears in any curated table.

| # | Class | What happens |
| --- | --- | --- |
| 1 | Names | dropped: surname, forenames, prefix, maiden surname, mother's maiden name, the `display` on every reference |
| 2 | Geography below state | street, town, coordinates, birthplace town dropped; ZIP to ZIP3, `000` for the seventeen small prefixes |
| 3 | Dates | offset per patient by up to 180 days; date of birth kept as the offset year; over 89 banded "90 and over" with no year |
| 4 to 6 | Phone, fax, email | dropped |
| 7, 8 | SSN, MRN | dropped; the validator never echoes their values in a rejection |
| 9 | Health plan number | dropped from the claim |
| 10, 12 | Account and vehicle numbers | never read from the bundle |
| 11 | Licence numbers | driver's licence and passport dropped |
| 13 | Device identifiers | `Device` resources are not read |
| 14, 15 | URLs, IP addresses | photo URL dropped; free-text columns swept |
| 16, 17 | Biometrics, photographs | dropped with the photo |
| 18 | Any other unique number | every resource id replaced by a keyed BLAKE2b digest; the narrative with its person seed dropped |

The digest and the offset both derive from `CARELAKE_SCRUB_SECRET`. The mapping
is never written. The laptop default secret exists so the pipeline runs with no
setup; the scheduled refresh refuses to start on it.

Two honest notes. Strict Safe Harbor keeps only the year of a date; I offset
instead because the care-gap windows need days, and I say so
([decision 2](docs/decisions/02-offset-dates.md)). And `facility_id` is
Synthea's organisation UUID, an institution not a person, kept as the facility
dimension's key; the UUID sweep in the tests skips that one column.

## Decisions

- [01 One JSON Schema per table drives the door, the parquet and the scrubber](docs/decisions/01-schema-does-three-jobs.md)
- [02 Offset dates instead of year-only](docs/decisions/02-offset-dates.md)
- [03 The history lives in the published feed](docs/decisions/03-history-in-the-feed.md)

Other choices, briefly. Rejected rows keep their resource and every problem,
and duplicates within a cohort are rejected too. Raw is read by the scrubber
and nothing else; dbt's one raw source is the reject table without its payload
column. A blood pressure is one FHIR Observation with two components, so the
reader emits the parent plus one row per component and the schema insists that
a leaf row carries a value. The payer of an encounter is the payer on its
non-pharmacy claim, because that is the only place Synthea's FHIR names one.

## Azure

Dormant until `CARELAKE_SINK=adls`. Then `carelake ship` (and the end of
`carelake all`) uploads `raw/`, `curated/`, `serving/` and the two feeds into
filesystems of the same names. The raw bundles themselves never leave the
laptop; only the parquet tables, rejects and manifests do.

`infra/storage.bicep` creates the account with hierarchical namespace, no
public access, TLS 1.2, seven-day soft delete, raw tiered to cool after sixty
days, and a monthly budget mailing at 80% of $1 actual and 100% forecast.
`infra/synapse_serving.sql` puts Synapse serverless views over the marts.

Setup, once:

1. Free account at https://azure.microsoft.com/free, Azure CLI installed, `az login`.
2. `.\infra\up.ps1 -AccountName <unique lowercase name> -AlertTo <email>`
3. Secrets for the weekly refresh:
   ```powershell
   gh secret set CARELAKE_ADLS_ACCOUNT --body <name>
   az storage account keys list -g rg-carelake -n <name> --query "[0].value" -o tsv | gh secret set CARELAKE_ADLS_KEY
   gh secret set CARELAKE_SCRUB_SECRET --body (-join ((1..48) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) }))
   ```
4. Upgrade the subscription to pay-as-you-go inside 30 days to keep the 12-month free amounts.

Cost: storage at $0.019 per GB per month and a few thousand operations; cents.
Event Hubs has no free tier, which is why the lake is batch per cohort and not
a stream; that edition fits the first-month credit and is on the list below.

## Feeds and refresh

`carelake feeds` writes `web/feeds/status.json` (this build: counts, the scrub
ledger, re-identification risk, the pairs, the care gaps, rejects, resource
types not read, dbt results) and `web/feeds/history.json` (one point per ISO
week). A run fetches the published history, upserts its week and writes the
merged list, so the series needs no state on the runner and no commits.

`refresh.yml` runs Thursdays (GitHub's cron is late by minutes to hours;
nothing depends on when): a 400-patient cohort seeded by the ISO week, every
stage, feeds verified by `tools/verify_feeds.py`, the page deployed, the lake
shipped when the Azure secrets exist. `check.yml` runs on every push: lint, the
unit tests, then a 35-patient cohort through every stage including dbt.

## Layout

```
schemas/           one JSON Schema per table: types, rules, x-phi, x-scrub, x-free-text
carelake/          settings, generate, extract, schemas, land, scrub, curate, serve, feeds, adls, __main__
dbt/               sources over curated parquet; core views; marts; seeds; tests; macros
web/               the page; feeds/ is written by the pipeline, not committed
infra/             storage.bicep, up.ps1, synapse_serving.sql
tools/             verify_feeds.py, the publish gate
tests/             74 tests; samples/ holds two trimmed Synthea bundles
docs/decisions/    why
.github/workflows/ check.yml, refresh.yml
```

## Limits

- Synthetic through and through. Synthea's modules decide who gets a statin;
  the numbers show the measures work, not how Illinois is doing.
- Safe Harbor style: dates offset, not reduced to years. Seasonality is gone.
- Eight resource types. DiagnosticReport, DocumentReference,
  ExplanationOfBenefit, CarePlan, CareTeam, AllergyIntolerance, ImagingStudy,
  Device, SupplyDelivery, MedicationAdministration, Provenance and Medication
  (resolved through prescriptions) are counted, not modelled.
- `patient_dim` is type 2 in shape and type 1 in practice, because Synthea
  never re-emits a patient.
- Batch per cohort, not a stream. The scheduled lake holds the week's cohort;
  the multi-cohort history exists in ADLS when shipping is on, and in
  `history.json` otherwise.
- Facility names are kept; clinician names are dropped even though neither is
  a patient identifier.
- 10.5% of patients remain unique on six quasi-identifiers. That is what a Safe
  Harbor release looks like.

## Assumptions I made

- Illinois, seed 7, as-of 2026-11-21, 1,500 living patients, deceased kept so `died_at` and the age cap are exercised.
- Statins by generic name in the RxNorm label; eligible window 40 to 75 at diagnosis; HbA1c is LOINC 4548-4.
- Chronic buckets are my grouping of Synthea's SNOMED codes (`dbt/seeds/chronic_groups.csv`); payer classes map Medicare, Medicaid and dual eligibility to `government`, `NO_INSURANCE` to `uninsured`, the rest to `commercial`.
- A patient's age bracket is the age on the cohort's as-of date.
- Weekly refresh at 400 patients. The feed holds the series, not the repository.
- Great Expectations and Purview are not here; dbt's tests are the quality gate and the dbt graph is the lineage.

## Next

- Event Hubs in front of Spark Structured Streaming inside the first-month credit, same schemas, scrubbing per micro-batch.
- A source that updates patients so `patient_dim` has versions to keep.
- DiagnosticReport and CarePlan as tables nine and ten.
- Purview over the four filesystems.
