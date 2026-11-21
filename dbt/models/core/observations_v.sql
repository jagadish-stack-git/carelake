select
    oid, parent_oid, pid, eid, status, category, system, code, label,
    taken_at, issued_at, num_value, unit, text_value, coded_value, coded_label, n_components,
    _cohort as cohort
from {{ source('curated', 'observations') }}
qualify row_number() over (partition by oid order by _cohort desc) = 1
