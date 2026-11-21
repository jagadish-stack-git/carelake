select cohort, min(as_of) as as_of, max(scrubbed_at) as scrubbed_at, max(scrub_version) as scrub_version
from {{ source('curated', 'tally') }}
group by 1
