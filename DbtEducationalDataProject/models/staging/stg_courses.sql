{{ config(materialized='view') }}

with source_data as (
    select
        course_id,
        course_code,
        course_name,
        description,
        credits,
        department_id,
        prerequisite_course_id,
        difficulty_level,
        case 
            when difficulty_level = 1 then 'Beginner'
            when difficulty_level = 2 then 'Intermediate'
            when difficulty_level = 3 then 'Advanced'
            when difficulty_level = 4 then 'Expert'
            when difficulty_level = 5 then 'Graduate'
            else 'Unknown'
        end as difficulty_description,
        case
            when credits <= 1 then 'Workshop'
            when credits = 2 then 'Seminar'
            when credits = 3 then 'Standard'
            when credits >= 4 then 'Intensive'
            else 'Other'
        end as credit_category,
        created_at
    from {{ source('raw_edu', 'courses') }}
)

select * from source_data