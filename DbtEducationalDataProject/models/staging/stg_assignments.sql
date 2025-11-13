{{ config(materialized='view') }}

with source_data as (
    select
        assignment_id,
        course_id,
        semester_id,
        assignment_name,
        assignment_type,
        due_date,
        max_points,
        weight_percentage,
        case
            when assignment_type ilike '%exam%' or assignment_type ilike '%test%' then 'Assessment'
            when assignment_type ilike '%project%' then 'Project'
            when assignment_type ilike '%homework%' or assignment_type ilike '%hw%' then 'Homework'
            when assignment_type ilike '%quiz%' then 'Quiz'
            when assignment_type ilike '%discussion%' then 'Discussion'
            when assignment_type ilike '%presentation%' then 'Presentation'
            else 'Other'
        end as assignment_category,
        case
            when current_date > due_date then 'Past Due'
            when current_date = due_date then 'Due Today'
            when due_date - current_date <= 7 then 'Due This Week'
            when due_date - current_date <= 30 then 'Due This Month'
            else 'Future'
        end as due_status,
        due_date - current_date as days_until_due,
        case
            when weight_percentage >= 30 then 'High Weight'
            when weight_percentage >= 15 then 'Medium Weight'
            when weight_percentage >= 5 then 'Low Weight'
            else 'Minimal Weight'
        end as weight_category,
        created_at
    from {{ source('raw_edu', 'assignments') }}
)

select * from source_data