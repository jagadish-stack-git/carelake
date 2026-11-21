select
    rxid, pid, eid, status, intent, category, system, code, label,
    written_at, prescriber_npi, for_cid, _cohort as cohort
from {{ source('curated', 'prescriptions') }}
qualify row_number() over (partition by rxid order by _cohort desc) = 1
