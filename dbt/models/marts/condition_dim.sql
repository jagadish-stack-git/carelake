with seen as (
    select system, code, any_value(label) as label, count(*) as diagnoses
    from {{ ref('conditions_v') }} group by 1, 2
)
select
    md5(s.system || '#' || s.code) as condition_sk,
    s.system, s.code, s.label,
    g.bucket,
    g.code is not null             as chronic,
    s.diagnoses
from seen s
left join {{ ref('chronic_groups') }} g on g.code = s.code
