-- grain: one recorded diagnosis
select
    c.cid,
    p.patient_sk,
    c.pid,
    c.eid,
    d.condition_sk,
    cast(strftime(c.onset, '%Y%m%d') as integer) as onset_day_key,
    c.system, c.code, c.label,
    d.chronic, d.bucket,
    c.clinical_status, c.verification, c.category,
    c.onset, c.abated,
    date_diff('day', c.onset, c.abated)          as days_active,
    case when p.birth_year is not null then year(c.onset) - p.birth_year end as age_at_onset,
    p.age_bracket,
    coalesce(e.payer, 'UNKNOWN')                 as payer,
    c.cohort
from {{ ref('conditions_v') }} c
left join {{ ref('patient_dim') }} p on p.pid = c.pid and p.current_row
left join {{ ref('condition_dim') }} d on d.system = c.system and d.code = c.code
left join {{ ref('encounter_fact') }} e on e.eid = c.eid
