select
    eid, pid, status, setting, kind_code, kind, began, ended,
    date_diff('minute', began, ended) as minutes,
    reason_code, reason, facility_id, facility, clinician_npi, site,
    _cohort as cohort
from {{ source('curated', 'encounters') }}
qualify row_number() over (partition by eid order by _cohort desc) = 1
