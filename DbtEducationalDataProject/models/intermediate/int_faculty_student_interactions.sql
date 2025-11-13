{{ config(materialized='view') }}

with faculty_student_connections as (
    select
        f.faculty_id,
        f.full_name,
        f.position,
        f.department_id,
        f.years_of_service,
        cs.course_id,
        cs.semester_id,
        e.student_id,
        e.grade,
        e.grade_points,
        e.attendance_percentage,
        e.grade_category,
        s.full_name as student_name,
        s.gpa as student_cumulative_gpa,
        s.academic_standing,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        c.credits,
        sem.semester_name,
        sem.academic_year,
        d.department_name
    from {{ ref('stg_faculty') }} f
    inner join {{ ref('stg_class_sessions') }} cs on f.faculty_id = cs.faculty_id
    inner join {{ ref('stg_courses') }} c on cs.course_id = c.course_id
    inner join {{ ref('stg_enrollments') }} e on c.course_id = e.course_id and cs.semester_id = e.semester_id
    inner join {{ ref('stg_students') }} s on e.student_id = s.student_id
    inner join {{ ref('stg_semesters') }} sem on cs.semester_id = sem.semester_id
    inner join {{ ref('stg_departments') }} d on f.department_id = d.department_id
),

faculty_teaching_effectiveness as (
    select
        faculty_id,
        full_name,
        position,
        department_name,
        years_of_service,
        count(distinct student_id) as total_unique_students_taught,
        count(distinct course_id) as unique_courses_taught,
        count(distinct semester_id) as semesters_taught,
        avg(grade_points) as avg_grade_given,
        avg(attendance_percentage) as avg_student_attendance,
        stddev(grade_points) as grade_consistency,
        count(case when grade_category = 'Excellent' then 1 end) as excellent_grades_given,
        count(case when grade_category = 'Good' then 1 end) as good_grades_given,
        count(case when grade_category = 'Satisfactory' then 1 end) as satisfactory_grades_given,
        count(case when grade_category = 'Poor' then 1 end) as poor_grades_given,
        count(case when grade_category = 'Failing' then 1 end) as failing_grades_given,
        round(
            count(case when grade_category in ('Excellent', 'Good', 'Satisfactory') then 1 end) * 100.0 / 
            nullif(count(case when grade_category != 'Unknown' then 1 end), 0), 2
        ) as student_success_rate,
        avg(student_cumulative_gpa) as avg_incoming_student_gpa,
        corr(student_cumulative_gpa, grade_points) as gpa_correlation_with_performance,
        avg(difficulty_level) as avg_course_difficulty_taught,
        sum(credits) as total_credit_hours_taught
    from faculty_student_connections
    group by faculty_id, full_name, position, department_name, years_of_service
),

student_faculty_exposure as (
    select
        student_id,
        student_name,
        student_cumulative_gpa,
        academic_standing,
        count(distinct faculty_id) as unique_faculty_encountered,
        count(distinct department_id) as departments_studied_in,
        avg(grade_points) as avg_grade_received,
        string_agg(distinct full_name, ', ' order by full_name) as faculty_list,
        count(case when position = 'Professor' then 1 end) as courses_with_professors,
        count(case when position = 'Associate Professor' then 1 end) as courses_with_assoc_professors,
        count(case when position = 'Assistant Professor' then 1 end) as courses_with_asst_professors,
        avg(years_of_service) as avg_faculty_experience,
        count(distinct course_id) as total_courses_taken
    from faculty_student_connections
    group by student_id, student_name, student_cumulative_gpa, academic_standing
),

interaction_quality_metrics as (
    select
        fte.*,
        case
            when fte.student_success_rate >= 90 then 'Exceptional Educator'
            when fte.student_success_rate >= 80 then 'Highly Effective Educator'
            when fte.student_success_rate >= 70 then 'Effective Educator'
            when fte.student_success_rate >= 60 then 'Adequate Educator'
            else 'Needs Improvement'
        end as teaching_effectiveness_category,
        case
            when fte.avg_student_attendance >= 95 then 'Highly Engaging'
            when fte.avg_student_attendance >= 85 then 'Engaging'
            when fte.avg_student_attendance >= 75 then 'Moderately Engaging'
            else 'Low Engagement'
        end as student_engagement_level,
        case
            when abs(fte.gpa_correlation_with_performance) >= 0.7 then 'Strong Predictor'
            when abs(fte.gpa_correlation_with_performance) >= 0.4 then 'Moderate Predictor'
            when abs(fte.gpa_correlation_with_performance) >= 0.2 then 'Weak Predictor'
            else 'No Predictive Value'
        end as prior_gpa_predictive_power,
        case
            when fte.grade_consistency <= 0.5 then 'Very Consistent Grading'
            when fte.grade_consistency <= 1.0 then 'Consistent Grading'
            when fte.grade_consistency <= 1.5 then 'Somewhat Inconsistent'
            else 'Inconsistent Grading'
        end as grading_consistency_level,
        round(fte.total_unique_students_taught::numeric / fte.semesters_taught, 2) as avg_students_per_semester
    from faculty_teaching_effectiveness fte
)

select 
    iqm.*,
    sfe.unique_faculty_encountered,
    sfe.avg_faculty_experience,
    sfe.courses_with_professors,
    sfe.courses_with_assoc_professors,
    sfe.courses_with_asst_professors
from interaction_quality_metrics iqm
left join student_faculty_exposure sfe on 1=1  -- This creates a cartesian product for analysis