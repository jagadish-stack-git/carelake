-- 1900 to 2035. Event dates are offset per patient, so this labels shifted
-- days; it says nothing about the real calendar.
with d as (select unnest(generate_series(date '1900-01-01', date '2035-12-31', interval 1 day))::date as day)
select
    cast(strftime(day, '%Y%m%d') as integer) as day_key,
    day,
    year(day)                                as yr,
    quarter(day)                             as qtr,
    month(day)                               as mon,
    strftime(day, '%b')                      as mon_abbr,
    cast(strftime(day, '%V') as integer)     as iso_week,
    isodow(day)                              as dow,
    isodow(day) in (6, 7)                    as weekend,
    date_trunc('week', day)::date            as week_of,
    date_trunc('month', day)::date           as month_of
from d
