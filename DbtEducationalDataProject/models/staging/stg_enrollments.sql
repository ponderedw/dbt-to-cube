{{ config(materialized='view') }}

with source_data as (
    select
        enrollment_id,
        student_id,
        course_id,
        semester_id,
        enrollment_date,
        completion_date,
        grade,
        grade_points,
        attendance_percentage,
        case 
            when grade in ('A+', 'A', 'A-') then 'Excellent'
            when grade in ('B+', 'B', 'B-') then 'Good'
            when grade in ('C+', 'C', 'C-') then 'Satisfactory'
            when grade in ('D+', 'D', 'D-') then 'Poor'
            when grade in ('F', 'WF') then 'Failing'
            when grade = 'W' then 'Withdrawn'
            when grade = 'I' then 'Incomplete'
            else 'Unknown'
        end as grade_category,
        case
            when completion_date is not null then 'Completed'
            when grade = 'W' then 'Withdrawn'
            when grade = 'I' then 'Incomplete'
            else 'In Progress'
        end as enrollment_status,
        case
            when attendance_percentage >= 95 then 'Excellent'
            when attendance_percentage >= 85 then 'Good'
            when attendance_percentage >= 75 then 'Acceptable'
            when attendance_percentage >= 65 then 'Poor'
            else 'Critical'
        end as attendance_level,
        created_at
    from {{ source('raw_edu', 'enrollments') }}
)

select * from source_data