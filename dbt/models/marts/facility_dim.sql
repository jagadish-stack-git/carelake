-- Organisations that hosted encounters or billed claims. Facility ids come from
-- Synthea's provider file and are stable across cohorts.
with refs as (
    select facility_id, facility from {{ ref('encounters_v') }} where facility_id is not null
    union all
    select facility_id, facility from {{ ref('claims_v') }} where facility_id is not null
)
select md5(facility_id) as facility_sk, facility_id, any_value(facility) as facility, count(*) as mentions
from refs group by facility_id
