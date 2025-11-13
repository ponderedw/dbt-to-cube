{{ config(materialized='view') }}

with faculty_courses as (
    select
        f.faculty_id,
        f.full_name as full_name,
        f.position,
        f.salary,
        f.department_id,
        f.years_of_service,
        f.salary_band,
        d.department_name,
        d.department_code,
        cs.course_id,
        cs.semester_id,
        cs.session_date,
        cs.session_time,
        cs.time_block,
        cs.attendance_count,
        c.course_code,
        c.course_name,
        c.credits,
        c.difficulty_level,
        sem.semester_name,
        sem.academic_year,
        e.enrollment_id,
        e.student_id
    from {{ ref('stg_faculty') }} f
    left join {{ ref('stg_departments') }} d on f.department_id = d.department_id
    left join {{ ref('stg_class_sessions') }} cs on f.faculty_id = cs.faculty_id
    left join {{ ref('stg_courses') }} c on cs.course_id = c.course_id
    left join {{ ref('stg_semesters') }} sem on cs.semester_id = sem.semester_id
    left join {{ ref('stg_enrollments') }} e on c.course_id = e.course_id and sem.semester_id = e.semester_id
),

faculty_metrics as (
    select
        faculty_id,
        full_name,
        position,
        salary,
        department_id,
        years_of_service,
        salary_band,
        department_name,
        department_code,
        count(distinct course_id) as unique_courses_taught,
        count(distinct semester_id) as semesters_active,
        count(distinct session_date) as total_class_sessions,
        count(distinct enrollment_id) as total_students_taught,
        avg(attendance_count) as avg_class_attendance,
        sum(credits) as total_credit_hours_taught,
        avg(difficulty_level) as avg_course_difficulty,
        count(case when time_block = 'Morning' then 1 end) as morning_sessions,
        count(case when time_block = 'Afternoon' then 1 end) as afternoon_sessions,
        count(case when time_block = 'Evening' then 1 end) as evening_sessions,
        round(salary / nullif(count(distinct course_id), 0), 2) as salary_per_course,
        round(salary / nullif(sum(credits), 0), 2) as salary_per_credit_hour
    from faculty_courses
    group by 
        faculty_id, full_name, position, salary, department_id, 
        years_of_service, salary_band, department_name, department_code
),

workload_analysis as (
    select
        *,
        case
            when unique_courses_taught >= 6 then 'Heavy Load'
            when unique_courses_taught >= 4 then 'Standard Load'
            when unique_courses_taught >= 2 then 'Light Load'
            when unique_courses_taught = 1 then 'Minimal Load'
            else 'No Teaching Load'
        end as teaching_load_category,
        case
            when total_credit_hours_taught >= 18 then 'Overloaded'
            when total_credit_hours_taught >= 12 then 'Full Load'
            when total_credit_hours_taught >= 6 then 'Part Load'
            else 'Minimal Load'
        end as credit_hour_load_category
    from faculty_metrics
)

select * from workload_analysis