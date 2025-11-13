{% macro calculate_gpa(grade_points_column, credits_column, partition_by=none) %}
    {% if partition_by %}
        round(
            sum({{ grade_points_column }} * {{ credits_column }}) over (partition by {{ partition_by }}) / 
            nullif(sum({{ credits_column }}) over (partition by {{ partition_by }}), 0), 
            2
        )
    {% else %}
        round(
            sum({{ grade_points_column }} * {{ credits_column }}) / 
            nullif(sum({{ credits_column }}), 0), 
            2
        )
    {% endif %}
{% endmacro %}