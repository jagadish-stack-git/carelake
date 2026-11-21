-- Synthea ids are UUIDs; one in a mart key means a row skipped the scrubber.
with k as (
    select pid as v from {{ ref('encounter_fact') }}
    union all select eid from {{ ref('encounter_fact') }}
    union all select pid from {{ ref('diagnosis_fact') }}
    union all select eid from {{ ref('diagnosis_fact') }}
    union all select pid from {{ ref('result_fact') }}
    union all select for_cid from {{ ref('prescription_fact') }}
)
select v from k
where v is not null and regexp_matches(v, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
