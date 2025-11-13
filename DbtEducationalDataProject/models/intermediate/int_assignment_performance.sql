{{ config(materialized='view') }}

with assignment_data as (
    select
        a.assignment_id,
        a.course_id,
        a.semester_id,
        a.assignment_name,
        a.assignment_type,
        a.assignment_category,
        a.due_date,
        a.due_status,
        a.max_points,
        a.weight_percentage,
        a.weight_category,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        sem.semester_name,
        sem.academic_year,
        sub.submission_id,
        sub.student_id,
        sub.submission_date,
        sub.score,
        sub.late_submission,
        sub.grading_status,
        sub.submission_timeliness,
        sub.feedback_status,
        s.full_name as student_name,
        s.gpa as student_gpa,
        s.academic_standing
    from {{ ref('stg_assignments') }} a
    left join {{ ref('stg_courses') }} c on a.course_id = c.course_id
    left join {{ ref('stg_semesters') }} sem on a.semester_id = sem.semester_id
    left join {{ ref('stg_assignment_submissions') }} sub on a.assignment_id = sub.assignment_id
    left join {{ ref('stg_students') }} s on sub.student_id = s.student_id
),

assignment_metrics as (
    select
        assignment_id,
        course_id,
        semester_id,
        assignment_name,
        assignment_type,
        assignment_category,
        due_date,
        due_status,
        max_points,
        weight_percentage,
        weight_category,
        course_code,
        course_name,
        difficulty_level,
        semester_name,
        academic_year,
        count(distinct submission_id) as total_submissions,
        count(distinct student_id) as unique_students_submitted,
        avg(score) as avg_score,
        min(score) as min_score,
        max(score) as max_score,
        stddev(score) as score_standard_deviation,
        avg(case when score is not null then score / max_points * 100 end) as avg_percentage_score,
        count(case when late_submission then 1 end) as late_submissions,
        count(case when grading_status = 'Graded' then 1 end) as graded_submissions,
        count(case when feedback_status = 'Has Feedback' then 1 end) as submissions_with_feedback,
        round(
            count(case when late_submission then 1 end) * 100.0 / 
            nullif(count(submission_id), 0), 2
        ) as late_submission_rate,
        round(
            count(case when grading_status = 'Graded' then 1 end) * 100.0 / 
            nullif(count(submission_id), 0), 2
        ) as grading_completion_rate,
        round(
            count(case when score >= max_points * 0.9 then 1 end) * 100.0 / 
            nullif(count(case when score is not null then 1 end), 0), 2
        ) as excellent_performance_rate,
        round(
            count(case when score < max_points * 0.6 then 1 end) * 100.0 / 
            nullif(count(case when score is not null then 1 end), 0), 2
        ) as poor_performance_rate
    from assignment_data
    where assignment_id is not null
    group by 
        assignment_id, course_id, semester_id, assignment_name, assignment_type, 
        assignment_category, due_date, due_status, max_points, weight_percentage, 
        weight_category, course_code, course_name, difficulty_level, semester_name, academic_year
)

select * from assignment_metrics