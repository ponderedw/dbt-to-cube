{{ config(materialized='table') }}

with faculty_dashboard as (
    select
        f.faculty_id,
        f.full_name,
        f.position,
        f.salary,
        f.years_of_service,
        f.salary_band,
        f.department_name,
        f.department_code,
        f.unique_courses_taught,
        f.semesters_active,
        f.total_class_sessions,
        f.total_students_taught,
        f.avg_class_attendance,
        f.total_credit_hours_taught,
        f.avg_course_difficulty,
        f.teaching_load_category,
        f.credit_hour_load_category,
        f.salary_per_course,
        f.salary_per_credit_hour,
        f.morning_sessions,
        f.afternoon_sessions,
        f.evening_sessions,
        da.avg_faculty_salary as dept_avg_salary,
        da.student_faculty_ratio as dept_student_faculty_ratio,
        round(f.salary / nullif(da.avg_faculty_salary, 0) * 100, 2) as salary_vs_dept_avg_percent,
        case
            when f.total_students_taught >= 200 then 'High Impact Teacher'
            when f.total_students_taught >= 100 then 'Moderate Impact Teacher'
            when f.total_students_taught >= 50 then 'Standard Impact Teacher'
            else 'Limited Impact Teacher'
        end as teaching_impact_category,
        case
            when f.avg_class_attendance >= 95 then 'Excellent Student Engagement'
            when f.avg_class_attendance >= 85 then 'Good Student Engagement'
            when f.avg_class_attendance >= 75 then 'Fair Student Engagement'
            else 'Poor Student Engagement'
        end as engagement_effectiveness,
        case
            when f.years_of_service >= 15 then 'Senior Faculty'
            when f.years_of_service >= 10 then 'Experienced Faculty'
            when f.years_of_service >= 5 then 'Mid-Career Faculty'
            else 'Junior Faculty'
        end as career_stage,
        round(f.total_students_taught::numeric / nullif(f.semesters_active, 0), 2) as avg_students_per_semester
    from {{ ref('int_faculty_teaching_load') }} f
    left join {{ ref('int_department_analytics') }} da on f.department_id = da.department_id
)

select * from faculty_dashboard