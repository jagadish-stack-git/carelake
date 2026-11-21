-- What the scrubber did, per table, summed across cohorts.
select
    table_name,
    max(scrub_version)        as scrub_version,
    count(distinct cohort)    as cohorts,
    sum(rows)                 as rows,
    any_value(dropped)        as dropped_columns,
    sum(hashed)               as ids_hashed,
    sum("offset")             as dates_offset,
    sum(zip3)                 as zips_truncated,
    sum(zip3_small)           as zips_zeroed,
    sum(over_89)              as ages_capped,
    sum(swept)                as free_text_redactions,
    max(scrubbed_at)          as last_scrubbed_at
from {{ source('curated', 'tally') }}
group by 1
order by 1
