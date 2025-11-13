{{ config(materialized='view') }}

with course_enrollments as (
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.credits,
        c.difficulty_level,
        c.difficulty_description,
        d.department_name,
        d.department_code,
        e.enrollment_id,
        e.student_id,
        e.semester_id,
        e.grade,
        e.grade_points,
        e.attendance_percentage,
        e.grade_category,
        e.enrollment_status,
        sem.semester_name,
        sem.academic_year,
        f.full_name as instructor_name,
        f.position as instructor_position
    from {{ ref('stg_courses') }} c
    left join {{ ref('stg_enrollments') }} e on c.course_id = e.course_id
    left join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    left join {{ ref('stg_class_sessions') }} cs on c.course_id = cs.course_id and sem.semester_id = cs.semester_id
    left join {{ ref('stg_faculty') }} f on cs.faculty_id = f.faculty_id
),

course_metrics as (
    select
        course_id,
        course_code,
        course_name,
        credits,
        difficulty_level,
        difficulty_description,
        department_name,
        department_code,
        count(distinct enrollment_id) as total_enrollments,
        count(distinct student_id) as unique_students,
        count(distinct semester_id) as semesters_offered,
        avg(grade_points) as avg_grade_points,
        avg(attendance_percentage) as avg_attendance,
        count(case when grade_category = 'Excellent' then 1 end) as excellent_grades,
        count(case when grade_category = 'Good' then 1 end) as good_grades,
        count(case when grade_category = 'Satisfactory' then 1 end) as satisfactory_grades,
        count(case when grade_category = 'Poor' then 1 end) as poor_grades,
        count(case when grade_category = 'Failing' then 1 end) as failing_grades,
        count(case when enrollment_status = 'Withdrawn' then 1 end) as withdrawals,
        round(
            count(case when grade_category in ('Excellent', 'Good', 'Satisfactory') then 1 end) * 100.0 / 
            nullif(count(case when grade_category != 'Unknown' then 1 end), 0), 2
        ) as pass_rate,
        round(
            count(case when enrollment_status = 'Withdrawn' then 1 end) * 100.0 / 
            nullif(count(enrollment_id), 0), 2
        ) as withdrawal_rate
    from course_enrollments
    where course_id is not null
    group by 
        course_id, course_code, course_name, credits, difficulty_level, 
        difficulty_description, department_name, department_code
)

select * from course_metrics