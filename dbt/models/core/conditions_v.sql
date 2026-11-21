select
    cid, pid, eid, clinical_status, verification, category, system, code, label,
    onset, abated, recorded, _cohort as cohort
from {{ source('curated', 'conditions') }}
qualify row_number() over (partition by cid order by _cohort desc) = 1
