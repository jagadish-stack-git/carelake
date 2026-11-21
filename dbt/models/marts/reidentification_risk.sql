-- k-anonymity over the quasi-identifiers that survive scrubbing:
-- age bracket, sex, race, ethnicity, region, ZIP3. Safe Harbor sets no k;
-- this mart reports the one the data actually has.
with grp as (
    select age_bracket, sex, race, ethnicity, region, zip3, count(*) as k
    from {{ ref('patient_dim') }} where current_row
    group by all
)
select
    sum(k)                                              as patients,
    count(*)                                            as groups,
    min(k)                                              as smallest_group,
    sum(k) filter (where k = 1)                         as unique_patients,
    round(sum(k) filter (where k = 1) / sum(k), 4)      as unique_share,
    round(sum(k) filter (where k < 5) / sum(k), 4)      as under_5_share,
    round(sum(k) filter (where k < 11) / sum(k), 4)     as under_11_share,
    'age_bracket, sex, race, ethnicity, region, zip3'   as quasi_identifiers
from grp
