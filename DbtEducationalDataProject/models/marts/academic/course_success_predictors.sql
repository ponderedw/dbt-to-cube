{{ config(materialized='table') }}

with course_student_data as (
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        c.credits,
        c.prerequisite_course_id,
        d.department_name,
        e.student_id,
        e.grade,
        e.grade_points,
        e.attendance_percentage,
        e.grade_category,
        e.enrollment_status,
        s.gpa as student_cumulative_gpa,
        s.academic_standing,
        s.age,
        s.years_enrolled,
        sem.semester_name,
        sem.semester_type,
        ap.total_submissions,
        ap.avg_percentage_score as avg_assignment_score,
        ap.late_submission_rate,
        case when e.grade_points >= 3.0 then 1 else 0 end as successful_completion,
        case when e.attendance_percentage >= 80 then 1 else 0 end as good_attendance,
        case when s.gpa >= 3.0 then 1 else 0 end as strong_academic_record
    from {{ ref('stg_courses') }} c
    inner join {{ ref('stg_enrollments') }} e on c.course_id = e.course_id
    inner join {{ ref('stg_students') }} s on e.student_id = s.student_id
    inner join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    inner join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    left join (
        select 
            course_id,
            avg(total_submissions) as total_submissions,
            avg(avg_percentage_score) as avg_percentage_score,
            avg(late_submission_rate) as late_submission_rate
        from {{ ref('int_assignment_performance') }}
        group by course_id
    ) ap on c.course_id = ap.course_id
    where e.enrollment_status = 'Completed'
),

success_factors as (
    select
        course_id,
        course_code,
        course_name,
        difficulty_level,
        credits,
        department_name,
        count(*) as total_completions,
        sum(successful_completion) as successful_completions,
        round(avg(successful_completion) * 100, 2) as success_rate,
        avg(grade_points) as avg_course_grade_points,
        avg(attendance_percentage) as avg_course_attendance,
        avg(student_cumulative_gpa) as avg_student_entering_gpa,
        avg(avg_assignment_score) as avg_assignment_performance,
        corr(student_cumulative_gpa, grade_points) as gpa_correlation,
        corr(attendance_percentage, grade_points) as attendance_correlation,
        corr(avg_assignment_score, grade_points) as assignment_correlation,
        corr(age, grade_points) as age_correlation,
        count(case when strong_academic_record = 1 and successful_completion = 1 then 1 end) as strong_students_successful,
        count(case when strong_academic_record = 1 then 1 end) as strong_students_total,
        count(case when good_attendance = 1 and successful_completion = 1 then 1 end) as good_attendance_successful,
        count(case when good_attendance = 1 then 1 end) as good_attendance_total,
        avg(case when semester_type = 'Fall' then grade_points end) as fall_avg_performance,
        avg(case when semester_type = 'Spring' then grade_points end) as spring_avg_performance,
        avg(case when semester_type = 'Summer' then grade_points end) as summer_avg_performance
    from course_student_data
    group by 
        course_id, course_code, course_name, difficulty_level, 
        credits, department_name
    having count(*) >= 3  -- Only courses with sufficient data
),

predictive_analysis as (
    select
        *,
        round(
            (strong_students_successful * 100.0) / nullif(strong_students_total, 0), 2
        ) as strong_student_success_rate,
        round(
            (good_attendance_successful * 100.0) / nullif(good_attendance_total, 0), 2
        ) as good_attendance_success_rate,
        case
            when success_rate >= 90 then 'Very High Success'
            when success_rate >= 75 then 'High Success'
            when success_rate >= 60 then 'Moderate Success'
            when success_rate >= 45 then 'Low Success'
            else 'Very Low Success'
        end as success_category,
        case
            when abs(gpa_correlation) >= 0.7 then 'Strong GPA Predictor'
            when abs(gpa_correlation) >= 0.4 then 'Moderate GPA Predictor'
            when abs(gpa_correlation) >= 0.2 then 'Weak GPA Predictor'
            else 'GPA Not Predictive'
        end as gpa_predictive_strength,
        case
            when abs(attendance_correlation) >= 0.7 then 'Strong Attendance Predictor'
            when abs(attendance_correlation) >= 0.4 then 'Moderate Attendance Predictor'
            when abs(attendance_correlation) >= 0.2 then 'Weak Attendance Predictor'
            else 'Attendance Not Predictive'
        end as attendance_predictive_strength,
        case
            when abs(assignment_correlation) >= 0.7 then 'Strong Assignment Predictor'
            when abs(assignment_correlation) >= 0.4 then 'Moderate Assignment Predictor'
            when abs(assignment_correlation) >= 0.2 then 'Weak Assignment Predictor'
            else 'Assignments Not Predictive'
        end as assignment_predictive_strength,
        case
            when fall_avg_performance > spring_avg_performance 
                 and fall_avg_performance > summer_avg_performance then 'Fall Best Performance'
            when spring_avg_performance > summer_avg_performance then 'Spring Best Performance'
            when summer_avg_performance is not null then 'Summer Best Performance'
            else 'No Clear Seasonal Pattern'
        end as seasonal_performance_pattern,
        case
            when difficulty_level <= 2 and success_rate >= 85 then 'Appropriately Difficult'
            when difficulty_level >= 4 and success_rate <= 60 then 'Appropriately Challenging'
            when difficulty_level <= 2 and success_rate <= 60 then 'Unexpectedly Difficult'
            when difficulty_level >= 4 and success_rate >= 85 then 'Easier Than Expected'
            else 'Standard Difficulty-Success Alignment'
        end as difficulty_alignment
    from success_factors
)

select * from predictive_analysis
order by success_rate desc