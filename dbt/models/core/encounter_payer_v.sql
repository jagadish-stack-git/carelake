-- Who paid for an encounter: the payer on its non-pharmacy claim. Earliest claim wins on a tie.
select eid, payer, clid
from {{ ref('claims_v') }}
where eid is not null and kind <> 'pharmacy'
qualify row_number() over (partition by eid order by created_at, clid) = 1
