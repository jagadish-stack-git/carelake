select
    x.prid, p.patient_sk, x.pid, x.eid,
    cast(strftime(x.began, '%Y%m%d') as integer) as began_day_key,
    x.status, x.system, x.code, x.label, x.began, x.ended,
    date_diff('minute', x.began, x.ended)        as minutes,
    x.for_cid, x.site, x.cohort
from {{ ref('procedures_v') }} x
left join {{ ref('patient_dim') }} p on p.pid = x.pid and p.current_row
