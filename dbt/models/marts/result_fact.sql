-- grain: one observed value; panel parents carry n_components > 0 and no value
select
    o.oid, o.parent_oid, p.patient_sk, o.pid, o.eid,
    cast(strftime(o.taken_at, '%Y%m%d') as integer) as taken_day_key,
    o.status, o.category, o.system, o.code, o.label, o.taken_at,
    o.num_value, o.unit, o.text_value, o.coded_value, o.coded_label, o.n_components, o.cohort
from {{ ref('observations_v') }} o
left join {{ ref('patient_dim') }} p on p.pid = o.pid and p.current_row
