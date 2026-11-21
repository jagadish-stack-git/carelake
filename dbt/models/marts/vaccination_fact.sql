select
    i.imid, p.patient_sk, i.pid, i.eid,
    cast(strftime(i.given_at, '%Y%m%d') as integer) as given_day_key,
    i.status, i.system, i.code, i.label, i.given_at, i.site, i.cohort
from {{ ref('immunizations_v') }} i
left join {{ ref('patient_dim') }} p on p.pid = i.pid and p.current_row
