# 01 One JSON Schema per table drives the door, the parquet and the scrubber

Accepted 2026-11-21.

## Problem

Eight tables, each with a validator, a parquet schema and a scrubbing rule per
column. Three descriptions of the same thing drift; the one that drifts is the
one nobody tests.

## Choice

`schemas/<table>.schema.json` is JSON Schema 2020-12 plus three vendor
keywords: `x-phi` (one of the eighteen Safe Harbor classes), `x-scrub` (`keep`,
`drop`, `hash`, `offset`, `zip3`, `dob_year`) and `x-free-text` (sweep the
value for identifier-shaped strings). `additionalProperties: false` so a reader
that emits an unexpected column fails at the door.

- `TableSchema.problems()` validates a row with the standard library validator,
  strips nulls first so a present-but-null required column counts as missing,
  then runs `x-rules` (`past`, `ordered`, `any_of`). Values of PHI columns are
  never echoed into a problem string.
- `arrow_raw()` and `arrow_curated()` derive the parquet schemas; `dob_year`
  becomes `birth_year`, `drop` columns vanish.
- `Scrubber.row()` dispatches on `x-scrub`.
- `tests/test_schemas.py` fails if any column with an `x-phi` class keeps.

## Consequences

Adding a table is one schema file and one reader function. Changing a rule
bumps `x-version`, which travels into the reject log so old and new rejections
can be told apart. The cost is that JSON Schema's `format` checks for dates are
not enforced by the library without an extra package, so the `x-rules`
evaluation is what proves a date parses.
