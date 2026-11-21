select * from {{ ref('diabetes_care_gaps') }}
where statin_in_year > statin_eligible or statin_eligible > diabetics or a1c_in_90d > diabetics
