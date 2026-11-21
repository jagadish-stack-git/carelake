{# exactly three digits, or null #}
{% test three_digit_zip(model, column_name) %}
select {{ column_name }} from {{ model }}
where {{ column_name }} is not null and not regexp_matches({{ column_name }}, '^\d{3}$')
{% endtest %}

{# a keyed BLAKE2b digest is 32 hex chars, optionally followed by #n for observation components #}
{% test digest_shape(model, column_name) %}
select {{ column_name }} from {{ model }}
where {{ column_name }} is not null and not regexp_matches({{ column_name }}, '^[0-9a-f]{32}(#\d+)?$')
{% endtest %}

{# one row per unordered pair #}
{% test one_row_per_pair(model) %}
select bucket_a, bucket_b from {{ model }} group by 1, 2 having count(*) > 1
{% endtest %}
