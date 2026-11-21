with seen as (select payer, count(*) as claims from {{ ref('claims_v') }} group by 1)
select
    md5(s.payer)                              as payer_sk,
    s.payer,
    coalesce(c.payer_class, 'commercial')     as payer_class,
    s.claims
from seen s
left join {{ ref('payer_classes') }} c using (payer)
