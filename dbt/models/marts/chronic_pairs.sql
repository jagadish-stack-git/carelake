-- Chronic buckets that share patients, with lift against independence
-- (both_n * N / (a_n * b_n); 1.0 means no association). Pairs under 10
-- patients are dropped as noise.
with n as (select count(*) as total from {{ ref('patient_dim') }} where current_row),
has as (select distinct pid, bucket from {{ ref('diagnosis_fact') }} where chronic),
singles as (select bucket, count(*) as patients from has group by 1),
pairs as (
    select a.bucket as bucket_a, b.bucket as bucket_b, count(*) as both_n
    from has a join has b on a.pid = b.pid and a.bucket < b.bucket
    group by 1, 2
)
select
    p.bucket_a, p.bucket_b, p.both_n,
    sa.patients as a_n, sb.patients as b_n, n.total,
    round(p.both_n / n.total, 4)                               as share,
    round(p.both_n * n.total / (sa.patients * sb.patients), 2) as lift,
    round(p.both_n / sa.patients, 4)                           as b_given_a,
    round(p.both_n / sb.patients, 4)                           as a_given_b
from pairs p
join singles sa on sa.bucket = p.bucket_a
join singles sb on sb.bucket = p.bucket_b
cross join n
where p.both_n >= 10
order by p.both_n desc
