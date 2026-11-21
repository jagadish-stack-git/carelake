select
    imid, pid, eid, status, system, code, label, given_at, site, _cohort as cohort
from {{ source('curated', 'immunizations') }}
qualify row_number() over (partition by imid order by _cohort desc) = 1
