{{ config(severity='warn') }}
-- Warn when more than half the patients sit in a quasi-identifier group under 5.
select * from {{ ref('reidentification_risk') }} where under_5_share > 0.5
