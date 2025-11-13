{{ config(materialized='table') }}

with student_summary as (
    select
        s.student_id,
        s.full_name,
        s.email,
        s.age,
        s.years_enrolled,
        s.student_status,
        s.gpa,
        s.academic_standing,
        s.current_status,
        d.department_name as major_department,
        d.department_code as major_code,
        eh.total_enrollments,
        eh.total_credits_attempted,
        eh.total_credits_earned,
        eh.failed_courses_count,
        eh.withdrawn_courses_count,
        eh.avg_grade_points,
        eh.avg_attendance,
        round(eh.total_credits_earned::numeric / nullif(eh.total_credits_attempted, 0) * 100, 2) as completion_rate,
        case
            when eh.total_credits_earned >= 120 then 'Graduation Ready'
            when eh.total_credits_earned >= 90 then 'Senior Standing'
            when eh.total_credits_earned >= 60 then 'Junior Standing'
            when eh.total_credits_earned >= 30 then 'Sophomore Standing'
            else 'Freshman Standing'
        end as class_standing,
        case
            when eh.failed_courses_count = 0 and eh.withdrawn_courses_count = 0 then 'Excellent Progress'
            when eh.failed_courses_count <= 1 and eh.withdrawn_courses_count <= 1 then 'Good Progress'
            when eh.failed_courses_count <= 3 or eh.withdrawn_courses_count <= 3 then 'At Risk'
            else 'Critical Status'
        end as progress_indicator
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join (
        select 
            student_id,
            max(total_enrollments) as total_enrollments,
            max(total_credits_attempted) as total_credits_attempted,
            max(total_credits_earned) as total_credits_earned,
            max(failed_courses_count) as failed_courses_count,
            max(withdrawn_courses_count) as withdrawn_courses_count,
            max(avg_grade_points) as avg_grade_points,
            max(avg_attendance) as avg_attendance
        from {{ ref('int_student_enrollment_history') }}
        group by student_id
    ) eh on s.student_id = eh.student_id
)

select * from student_summary