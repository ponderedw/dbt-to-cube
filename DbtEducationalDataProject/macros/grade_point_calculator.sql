{% macro grade_point_calculator(grade_column) %}
    case 
        when {{ grade_column }} = 'A+' then 4.0
        when {{ grade_column }} = 'A' then 4.0
        when {{ grade_column }} = 'A-' then 3.7
        when {{ grade_column }} = 'B+' then 3.3
        when {{ grade_column }} = 'B' then 3.0
        when {{ grade_column }} = 'B-' then 2.7
        when {{ grade_column }} = 'C+' then 2.3
        when {{ grade_column }} = 'C' then 2.0
        when {{ grade_column }} = 'C-' then 1.7
        when {{ grade_column }} = 'D+' then 1.3
        when {{ grade_column }} = 'D' then 1.0
        when {{ grade_column }} = 'D-' then 0.7
        when {{ grade_column }} in ('F', 'WF') then 0.0
        else null
    end
{% endmacro %}