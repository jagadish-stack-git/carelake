-- After a first type 2 diabetes diagnosis:
--   statin_in_year  statin ordered within 365 days, among patients aged 40 to 75 at diagnosis
--   a1c_in_90d      HbA1c (LOINC 4548-4) resulted within 90 days, among everyone
-- Each patient's dates share one offset, so the windows are exact.
with first_dx as (
    select pid,
           min(onset)                      as dx_at,
           any_value(age_bracket)          as age_bracket,
           min_by(payer, onset)            as payer,
           min_by(age_at_onset, onset)     as age_at_dx
    from {{ ref('diagnosis_fact') }}
    where bucket = 'T2 diabetes'
    group by 1
),
statin as (
    select d.pid from first_dx d
    join {{ ref('prescription_fact') }} r
      on r.pid = d.pid and r.statin and r.written_at >= d.dx_at and r.written_at < d.dx_at + interval 365 day
    group by 1
),
a1c as (
    select d.pid from first_dx d
    join {{ ref('result_fact') }} o
      on o.pid = d.pid and o.code = '4548-4' and o.taken_at >= d.dx_at and o.taken_at < d.dx_at + interval 90 day
    group by 1
),
scored as (
    select
        d.pid, d.age_bracket,
        coalesce(y.payer_class, case when d.payer = 'UNKNOWN' then 'unknown' else 'commercial' end) as payer_class,
        d.age_at_dx between 40 and 75 as statin_eligible,
        s.pid is not null             as statin_in_year,
        a.pid is not null             as a1c_in_90d
    from first_dx d
    left join {{ ref('payer_dim') }} y on y.payer = d.payer
    left join statin s using (pid)
    left join a1c a using (pid)
)
select
    age_bracket, payer_class,
    count(*)                                                   as diabetics,
    count(*) filter (where statin_eligible)                    as statin_eligible,
    count(*) filter (where statin_eligible and statin_in_year) as statin_in_year,
    count(*) filter (where a1c_in_90d)                         as a1c_in_90d
from scored
group by 1, 2
order by 1, 2
