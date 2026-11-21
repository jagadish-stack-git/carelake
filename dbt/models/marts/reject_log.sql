-- Rejected rows by table and problem (field name only). A row with two
-- problems counts under each.
with split as (
    select table_name, schema_version, resource_type, cohort,
           trim(split_part(unnest(string_split(problems, ' | ')), ':', 1)) as problem,
           landed_at
    from {{ source('raw', 'rejects') }}
)
select table_name, schema_version, resource_type, cohort, problem, count(*) as n, max(landed_at) as last_seen
from split
group by 1, 2, 3, 4, 5
order by n desc
