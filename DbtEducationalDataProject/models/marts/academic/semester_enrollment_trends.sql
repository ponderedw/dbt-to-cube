{{ config(materialized='table') }}

with semester_data as (
    select
        sem.semester_id,
        sem.semester_name,
        sem.academic_year,
        sem.semester_type,
        sem.start_date,
        sem.end_date,
        sem.semester_duration_days,
        sem.semester_status,
        count(distinct e.enrollment_id) as total_enrollments,
        count(distinct e.student_id) as unique_students,
        count(distinct e.course_id) as unique_courses,
        count(distinct d.department_id) as departments_with_enrollments,
        avg(e.grade_points) as avg_semester_grade_points,
        avg(e.attendance_percentage) as avg_semester_attendance,
        sum(c.credits) as total_credit_hours_enrolled,
        count(case when e.grade_category = 'Excellent' then 1 end) as excellent_grades,
        count(case when e.grade_category = 'Good' then 1 end) as good_grades,
        count(case when e.grade_category = 'Satisfactory' then 1 end) as satisfactory_grades,
        count(case when e.grade_category = 'Poor' then 1 end) as poor_grades,
        count(case when e.grade_category = 'Failing' then 1 end) as failing_grades,
        count(case when e.enrollment_status = 'Withdrawn' then 1 end) as withdrawals,
        count(case when s.academic_standing = 'Dean''s List' then 1 end) as deans_list_students,
        count(case when s.academic_standing = 'Academic Probation' then 1 end) as probation_students,
        avg(c.difficulty_level) as avg_course_difficulty
    from {{ ref('stg_semesters') }} sem
    left join {{ ref('stg_enrollments') }} e on sem.semester_id = e.semester_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_students') }} s on e.student_id = s.student_id
    left join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    group by 
        sem.semester_id, sem.semester_name, sem.academic_year, sem.semester_type,
        sem.start_date, sem.end_date, sem.semester_duration_days, sem.semester_status
),

trend_analysis as (
    select
        *,
        lag(total_enrollments) over (order by start_date) as prev_semester_enrollments,
        lag(unique_students) over (order by start_date) as prev_semester_students,
        lag(avg_semester_grade_points) over (order by start_date) as prev_semester_gpa,
        round(
            (total_enrollments - lag(total_enrollments) over (order by start_date)) * 100.0 / 
            nullif(lag(total_enrollments) over (order by start_date), 0), 2
        ) as enrollment_growth_rate,
        round(
            (unique_students - lag(unique_students) over (order by start_date)) * 100.0 / 
            nullif(lag(unique_students) over (order by start_date), 0), 2
        ) as student_growth_rate,
        round(
            (excellent_grades + good_grades + satisfactory_grades) * 100.0 / 
            nullif(total_enrollments, 0), 2
        ) as success_rate,
        round(withdrawals * 100.0 / nullif(total_enrollments, 0), 2) as withdrawal_rate,
        round(total_credit_hours_enrolled::numeric / nullif(unique_students, 0), 2) as avg_credit_load_per_student,
        round(deans_list_students * 100.0 / nullif(unique_students, 0), 2) as deans_list_percentage,
        round(probation_students * 100.0 / nullif(unique_students, 0), 2) as probation_percentage
    from semester_data
),

seasonal_patterns as (
    select
        semester_type,
        count(*) as semester_count,
        avg(total_enrollments) as avg_enrollments_by_season,
        avg(unique_students) as avg_students_by_season,
        avg(success_rate) as avg_success_rate_by_season,
        avg(withdrawal_rate) as avg_withdrawal_rate_by_season,
        avg(avg_semester_grade_points) as avg_gpa_by_season,
        avg(avg_credit_load_per_student) as avg_credit_load_by_season
    from trend_analysis
    group by semester_type
),

performance_categories as (
    select
        ta.*,
        sp.avg_enrollments_by_season,
        sp.avg_success_rate_by_season,
        sp.avg_withdrawal_rate_by_season,
        sp.avg_gpa_by_season,
        case
            when success_rate >= 85 then 'High Performing Semester'
            when success_rate >= 70 then 'Good Performing Semester'
            when success_rate >= 60 then 'Average Performing Semester'
            else 'Low Performing Semester'
        end as semester_performance_category,
        case
            when withdrawal_rate <= 5 then 'Low Attrition'
            when withdrawal_rate <= 10 then 'Moderate Attrition'
            when withdrawal_rate <= 15 then 'High Attrition'
            else 'Very High Attrition'
        end as attrition_category,
        case
            when enrollment_growth_rate > 10 then 'High Growth'
            when enrollment_growth_rate > 0 then 'Positive Growth'
            when enrollment_growth_rate = 0 then 'No Growth'
            when enrollment_growth_rate > -10 then 'Decline'
            else 'Significant Decline'
        end as growth_category,
        case
            when avg_credit_load_per_student >= 15 then 'Heavy Course Load'
            when avg_credit_load_per_student >= 12 then 'Standard Course Load'
            when avg_credit_load_per_student >= 9 then 'Light Course Load'
            else 'Very Light Course Load'
        end as course_load_category
    from trend_analysis ta
    left join seasonal_patterns sp on ta.semester_type = sp.semester_type
)

select * from performance_categories
order by start_date