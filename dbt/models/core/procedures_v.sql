select
    prid, pid, eid, status, system, code, label, began, ended, for_cid, site, _cohort as cohort
from {{ source('curated', 'procedures') }}
qualify row_number() over (partition by prid order by _cohort desc) = 1
