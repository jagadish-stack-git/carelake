-- grain: one medication order
select
    r.rxid, p.patient_sk, r.pid, r.eid, d.drug_sk,
    cast(strftime(r.written_at, '%Y%m%d') as integer) as written_day_key,
    r.system, r.code, r.label, d.statin,
    r.status, r.intent, r.category, r.written_at, r.prescriber_npi, r.for_cid, r.cohort
from {{ ref('prescriptions_v') }} r
left join {{ ref('patient_dim') }} p on p.pid = r.pid and p.current_row
left join {{ ref('drug_dim') }} d on d.system = r.system and d.code = r.code
