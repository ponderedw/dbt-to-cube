{% macro test_referential_integrity(model, column, ref_model, ref_column) %}
  select count(*)
  from {{ model }}
  where {{ column }} is not null
    and {{ column }} not in (
      select {{ ref_column }}
      from {{ ref_model }}
      where {{ ref_column }} is not null
    )
{% endmacro %}