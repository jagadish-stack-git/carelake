# 03 The history lives in the published feed

Accepted 2026-11-21.

## Problem

The page wants a series over weeks. GitHub Actions runners are stateless,
Pages serves static files, and committing parquet from a workflow grows the
repository every week. The full multi-cohort lake belongs in ADLS Gen2 when
shipping is on, but the page must work without Azure.

## Choice

Each refresh generates one cohort seeded by the ISO week (`w202647`, seed
202647, as-of its Monday), so a re-run in the same week regenerates the same
patients. After the build, `carelake feeds` fetches the currently published
`history.json`, upserts this week's point by `week`, and publishes the merged
list. `status.json` describes the latest build only.

## Consequences

- No runner state, no commits. A lost Pages deployment loses that week's
  point and the next run carries on.
- The lake on the runner holds only the week's cohort. With
  `CARELAKE_SINK=adls` every cohort's raw, curated and serving layers also land
  in ADLS, where `patient_dim`'s versioning and the multi-cohort reports mean
  something.
- `--fresh` skips the fetch; local runs and the check workflow use it.
