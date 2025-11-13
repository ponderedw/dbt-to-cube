{% macro academic_year_from_date(date_column) %}
    case 
        when extract(month from {{ date_column }}) >= 8 then 
            extract(year from {{ date_column }})::text || '-' || (extract(year from {{ date_column }}) + 1)::text
        else 
            (extract(year from {{ date_column }}) - 1)::text || '-' || extract(year from {{ date_column }})::text
    end
{% endmacro %}