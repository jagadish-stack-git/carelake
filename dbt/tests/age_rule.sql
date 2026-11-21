-- Anyone over 89 is "90 and over" with no birth year; nobody else may read as older than 90.
select pid, birth_year, age_bracket, over_89
from {{ ref('patient_dim') }}
where (over_89 and birth_year is not null)
   or (over_89 and age_bracket <> '90 and over')
   or (not over_89 and age_bracket = '90 and over')
   or (birth_year is not null and year(current_date) - birth_year > 91)
