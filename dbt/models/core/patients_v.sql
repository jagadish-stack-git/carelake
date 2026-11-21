-- The newest row per patient digest wins if a cohort ever re-emits one.
select
    pid, sex, sex_at_birth, birth_year, age_bracket, over_89,
    died_at, died_at is not null as deceased,
    marital, race, ethnicity, multiple_birth, lang,
    region, zip as zip3, country, born_region,
    _cohort as cohort, _scrub_v as scrub_version
from {{ source('curated', 'patients') }}
qualify row_number() over (partition by pid order by _cohort desc) = 1
