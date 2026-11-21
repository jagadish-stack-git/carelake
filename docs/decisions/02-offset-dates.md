# 02 Offset dates instead of year-only

Accepted 2026-11-21.

## Problem

Safe Harbor's third class removes every element of a date except the year.
Read literally, a lab result would carry only "2021". The two measures this
lake answers need to know whether a statin was ordered within 365 days of a
diagnosis and whether an HbA1c came back within 90.

## Choice

Every date of a patient moves by the same offset, drawn from a keyed BLAKE2b
digest of the patient id, in [-180, 180] days and never zero. Intervals inside
one record are exact; absolute positions are wrong by up to half a year by an
amount nobody can compute without the secret. Date of birth becomes the offset
year, and anyone over 89 is "90 and over" with no year at all, which is the
Safe Harbor age rule.

## Consequences

- The README and the page call this Safe Harbor *style*. Offsetting is normal
  practice in de-identified research sets; a strict Safe Harbor release would
  keep years only.
- Seasonality is destroyed on purpose; `calendar_dim` labels shifted days.
- The offset is never stored. Undoing it needs the secret, which lives in the
  environment and nowhere in the data.
