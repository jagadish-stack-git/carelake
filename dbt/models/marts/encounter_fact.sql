-- grain: one encounter
select
    e.eid,
    p.patient_sk,
    e.pid,
    cast(strftime(e.began, '%Y%m%d') as integer) as began_day_key,
    f.facility_sk,
    y.payer_sk,
    coalesce(y.payer, 'UNKNOWN')                 as payer,
    e.status, e.setting, e.kind_code, e.kind,
    e.began, e.ended, e.minutes,
    case when p.birth_year is not null then year(e.began) - p.birth_year end as age_at_visit,
    p.age_bracket,
    e.reason_code, e.reason, e.clinician_npi, e.facility_id,
    e.cohort
from {{ ref('encounters_v') }} e
left join {{ ref('patient_dim') }} p on p.pid = e.pid and p.current_row
left join {{ ref('facility_dim') }} f on f.facility_id = e.facility_id
left join {{ ref('encounter_payer_v') }} ep on ep.eid = e.eid
left join {{ ref('payer_dim') }} y on y.payer = ep.payer
