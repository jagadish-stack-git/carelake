-- Nothing in core or marts may carry a column named like a direct identifier.
select table_schema, table_name, column_name
from information_schema.columns
where table_schema in ('core', 'marts')
  and regexp_matches(lower(column_name),
      '(^|_)(surname|forenames|family|prefix|ssn|tel|phone|fax|mail|email|street|town|city|zip$|zipcode|postal|license|licence|passport|maiden|mrn|member_no|lat|lng|longitude|latitude|narrative|photo|dob|birth_date)($|_)')
