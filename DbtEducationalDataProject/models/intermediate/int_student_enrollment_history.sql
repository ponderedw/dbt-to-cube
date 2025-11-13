{{ config(materialized='view') }}

with student_enrollments as (
    select
        s.student_id,
        s.full_name,
        s.email,
        s.student_status,
        s.gpa,
        s.academic_standing,
        e.enrollment_id,
        e.course_id,
        e.semester_id,
        e.grade,
        e.grade_points,
        e.attendance_percentage,
        e.grade_category,
        e.enrollment_status,
        c.course_code,
        c.course_name,
        c.credits,
        c.difficulty_level,
        sem.semester_name,
        sem.academic_year,
        sem.semester_type,
        d.department_name,
        d.department_code
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_enrollments') }} e on s.student_id = e.student_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    left join {{ ref('stg_departments') }} d on c.department_id = d.department_id
),

enrollment_metrics as (
    select
        *,
        row_number() over (partition by student_id order by semester_name) as enrollment_sequence,
        count(*) over (partition by student_id) as total_enrollments,
        avg(grade_points) over (partition by student_id) as avg_grade_points,
        avg(attendance_percentage) over (partition by student_id) as avg_attendance,
        sum(credits) over (partition by student_id) as total_credits_attempted,
        sum(case when grade_category in ('Excellent', 'Good', 'Satisfactory') then credits else 0 end) 
            over (partition by student_id) as total_credits_earned,
        count(case when grade_category = 'Failing' then 1 end) 
            over (partition by student_id) as failed_courses_count,
        count(case when enrollment_status = 'Withdrawn' then 1 end) 
            over (partition by student_id) as withdrawn_courses_count
    from student_enrollments
)

select * from enrollment_metrics