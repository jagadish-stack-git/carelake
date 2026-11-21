-- Slowly changing patient dimension, type 2. A later cohort that re-emits a
-- patient with different attributes closes the open row and opens a new one.
-- Synthea does not re-emit patients, so each has one row today; the shape is
-- here for a source that does.
with attrs as (
    select
        p.*,
        c.scrubbed_at,
        md5(concat_ws('|', coalesce(sex, ''), coalesce(sex_at_birth, ''), coalesce(birth_year::varchar, ''),
            coalesce(age_bracket, ''), coalesce(marital, ''), coalesce(race, ''), coalesce(ethnicity, ''),
            coalesce(region, ''), coalesce(zip3, ''), coalesce(deceased::varchar, ''), coalesce(lang, ''))) as fingerprint
    from {{ ref('patients_v') }} p
    left join {{ ref('cohorts_v') }} c using (cohort)
),
runs as (
    select
        *,
        lag(fingerprint) over (partition by pid order by scrubbed_at) as prev_fingerprint,
        lead(scrubbed_at) over (partition by pid order by scrubbed_at) as closed_at
    from attrs
)
select
    md5(pid || '/' || fingerprint)              as patient_sk,
    pid,
    sex, sex_at_birth, birth_year, age_bracket, over_89, deceased, died_at,
    marital, race, ethnicity, multiple_birth, lang, region, zip3, country, born_region,
    cohort,
    coalesce(scrubbed_at, timestamp '1900-01-01') as opened_at,
    closed_at,
    closed_at is null                           as current_row,
    fingerprint
from runs
where prev_fingerprint is null or prev_fingerprint <> fingerprint
