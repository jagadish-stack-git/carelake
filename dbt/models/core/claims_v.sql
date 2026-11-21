select
    clid, pid, eid, status, kind, use, period_from, period_to, created_at,
    facility_id, facility, payer, amount, currency, n_diagnoses, n_items, _cohort as cohort
from {{ source('curated', 'claims') }}
qualify row_number() over (partition by clid order by _cohort desc) = 1
