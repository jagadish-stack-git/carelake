with seen as (
    select system, code, any_value(label) as label, count(*) as prescriptions
    from {{ ref('prescriptions_v') }} group by 1, 2
)
select
    md5(system || '#' || code) as drug_sk,
    system, code, label,
    -- the statin family by generic name, used by the diabetes care-gap mart
    regexp_matches(lower(coalesce(label, '')),
        '(atorvastatin|simvastatin|rosuvastatin|pravastatin|lovastatin|fluvastatin|pitavastatin)') as statin,
    prescriptions
from seen
