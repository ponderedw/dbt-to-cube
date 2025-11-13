{{ config(materialized='table') }}

with course_learning_outcomes as (
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        c.credits,
        d.department_name,
        cpm.avg_grade_points,
        cpm.pass_rate,
        cpm.withdrawal_rate,
        cpm.avg_attendance,
        ap.avg_percentage_score as assignment_performance,
        ap.late_submission_rate,
        csp.gpa_correlation,
        csp.attendance_correlation,
        csp.assignment_correlation,
        case
            when cpm.avg_grade_points >= 3.5 then 'Exceeds Expectations'
            when cpm.avg_grade_points >= 3.0 then 'Meets Expectations'
            when cpm.avg_grade_points >= 2.5 then 'Approaching Expectations'
            else 'Below Expectations'
        end as grade_performance_level,
        case
            when cpm.pass_rate >= 90 then 'Excellent Mastery'
            when cpm.pass_rate >= 80 then 'Good Mastery'
            when cpm.pass_rate >= 70 then 'Acceptable Mastery'
            when cpm.pass_rate >= 60 then 'Poor Mastery'
            else 'Very Poor Mastery'
        end as content_mastery_level
    from {{ ref('stg_courses') }} c
    inner join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('int_course_performance_metrics') }} cpm on c.course_id = cpm.course_id
    left join (
        select 
            course_id,
            avg(avg_percentage_score) as avg_percentage_score,
            avg(late_submission_rate) as late_submission_rate
        from {{ ref('int_assignment_performance') }}
        group by course_id
    ) ap on c.course_id = ap.course_id
    left join {{ ref('course_success_predictors') }} csp on c.course_id = csp.course_id
),

student_learning_progression as (
    select
        s.student_id,
        s.full_name,
        s.gpa,
        s.academic_standing,
        d.department_name as major,
        eh.total_credits_earned,
        eh.avg_grade_points,
        count(distinct e.course_id) as courses_completed,
        avg(c.difficulty_level) as avg_course_difficulty,
        count(case when clo.content_mastery_level in ('Excellent Mastery', 'Good Mastery') then 1 end) as well_mastered_courses,
        count(case when clo.content_mastery_level in ('Poor Mastery', 'Very Poor Mastery') then 1 end) as poorly_mastered_courses,
        avg(case when c.difficulty_level = 1 then e.grade_points end) as avg_beginner_performance,
        avg(case when c.difficulty_level = 2 then e.grade_points end) as avg_intermediate_performance,
        avg(case when c.difficulty_level >= 3 then e.grade_points end) as avg_advanced_performance,
        stddev(e.grade_points) as performance_consistency
    from {{ ref('stg_students') }} s
    inner join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join (
        select 
            student_id,
            max(total_credits_earned) as total_credits_earned,
            max(avg_grade_points) as avg_grade_points
        from {{ ref('int_student_enrollment_history') }}
        group by student_id
    ) eh on s.student_id = eh.student_id
    left join {{ ref('stg_enrollments') }} e on s.student_id = e.student_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join course_learning_outcomes clo on c.course_id = clo.course_id
    where e.enrollment_status = 'Completed'
    group by 
        s.student_id, s.full_name, s.gpa, s.academic_standing, 
        d.department_name, eh.total_credits_earned, eh.avg_grade_points
),

learning_outcome_analysis as (
    select
        slp.*,
        case
            when avg_beginner_performance is not null and avg_intermediate_performance is not null then
                avg_intermediate_performance - avg_beginner_performance
            else null
        end as beginner_to_intermediate_growth,
        case
            when avg_intermediate_performance is not null and avg_advanced_performance is not null then
                avg_advanced_performance - avg_intermediate_performance
            else null
        end as intermediate_to_advanced_growth,
        case
            when avg_beginner_performance is not null and avg_advanced_performance is not null then
                avg_advanced_performance - avg_beginner_performance
            else null
        end as overall_learning_growth,
        round(
            well_mastered_courses * 100.0 / nullif(courses_completed, 0), 2
        ) as mastery_success_rate,
        case
            when performance_consistency <= 0.5 then 'Very Consistent'
            when performance_consistency <= 1.0 then 'Consistent'
            when performance_consistency <= 1.5 then 'Moderately Consistent'
            else 'Inconsistent'
        end as performance_consistency_level,
        case
            when avg_advanced_performance >= avg_beginner_performance + 0.5 then 'Strong Learning Growth'
            when avg_advanced_performance >= avg_beginner_performance + 0.2 then 'Moderate Learning Growth'
            when avg_advanced_performance >= avg_beginner_performance - 0.2 then 'Stable Performance'
            else 'Declining Performance'
        end as learning_trajectory
    from student_learning_progression slp
),

departmental_outcomes as (
    select
        major,
        count(*) as students_in_major,
        avg(gpa) as major_avg_gpa,
        avg(mastery_success_rate) as avg_mastery_rate,
        avg(overall_learning_growth) as avg_learning_growth,
        count(case when learning_trajectory = 'Strong Learning Growth' then 1 end) as strong_learners,
        count(case when learning_trajectory = 'Declining Performance' then 1 end) as declining_learners,
        round(
            count(case when learning_trajectory = 'Strong Learning Growth' then 1 end) * 100.0 / count(*), 2
        ) as strong_learner_percentage,
        avg(avg_course_difficulty) as major_avg_difficulty
    from learning_outcome_analysis
    group by major
),

course_outcome_effectiveness as (
    select
        clo.*,
        dept_out.avg_mastery_rate as dept_avg_mastery_rate,
        dept_out.avg_learning_growth as dept_avg_learning_growth,
        case
            when clo.pass_rate > dept_out.avg_mastery_rate * 1.1 then 'Above Department Average'
            when clo.pass_rate < dept_out.avg_mastery_rate * 0.9 then 'Below Department Average'
            else 'Near Department Average'
        end as relative_effectiveness,
        -- Learning outcome achievement score
        round(
            (case when grade_performance_level = 'Exceeds Expectations' then 30
                  when grade_performance_level = 'Meets Expectations' then 25
                  when grade_performance_level = 'Approaching Expectations' then 15
                  else 5 end) +
            (case when content_mastery_level = 'Excellent Mastery' then 25
                  when content_mastery_level = 'Good Mastery' then 20
                  when content_mastery_level = 'Acceptable Mastery' then 15
                  else 5 end) +
            (case when withdrawal_rate <= 5 then 20
                  when withdrawal_rate <= 10 then 15
                  when withdrawal_rate <= 15 then 10
                  else 5 end) +
            (case when avg_attendance >= 90 then 15
                  when avg_attendance >= 80 then 12
                  when avg_attendance >= 70 then 8
                  else 3 end) +
            (case when assignment_performance >= 85 then 10
                  when assignment_performance >= 75 then 8
                  when assignment_performance >= 65 then 5
                  else 2 end), 0
        ) as learning_outcome_score
    from course_learning_outcomes clo
    left join departmental_outcomes dept_out on clo.department_name = dept_out.major
),

final_assessment as (
    select
        loa.*,
        dept_out.major_avg_gpa,
        dept_out.strong_learner_percentage as dept_strong_learner_rate,
        dept_out.major_avg_difficulty as dept_avg_difficulty,
        case
            when overall_learning_growth > 0.5 and mastery_success_rate > 80 then 'Exceptional Learning Outcomes'
            when overall_learning_growth > 0.2 and mastery_success_rate > 70 then 'Strong Learning Outcomes'
            when overall_learning_growth > 0 and mastery_success_rate > 60 then 'Adequate Learning Outcomes'
            when overall_learning_growth <= 0 or mastery_success_rate <= 50 then 'Poor Learning Outcomes'
            else 'Mixed Learning Outcomes'
        end as overall_learning_outcome_assessment,
        case
            when learning_trajectory = 'Strong Learning Growth' and performance_consistency_level in ('Very Consistent', 'Consistent') then
                'Ready for advanced coursework and independent study'
            when learning_trajectory = 'Moderate Learning Growth' and mastery_success_rate >= 70 then
                'Progressing well, continue current academic plan'
            when learning_trajectory = 'Stable Performance' and mastery_success_rate >= 60 then
                'Consider academic enrichment activities'
            when learning_trajectory = 'Declining Performance' or mastery_success_rate < 50 then
                'Requires academic intervention and support'
            else 'Monitor progress and provide targeted support'
        end as learning_outcome_recommendation,
        -- Student readiness for next level
        case
            when avg_advanced_performance >= 3.0 and mastery_success_rate >= 80 then 'Ready for Graduate Studies'
            when avg_advanced_performance >= 2.5 and mastery_success_rate >= 70 then 'Ready for Senior Capstone'
            when avg_intermediate_performance >= 2.5 and total_credits_earned >= 60 then 'Ready for Advanced Courses'
            when avg_beginner_performance >= 2.0 and total_credits_earned >= 30 then 'Ready for Intermediate Courses'
            else 'Continue Foundation Building'
        end as academic_readiness_level
    from learning_outcome_analysis loa
    left join departmental_outcomes dept_out on loa.major = dept_out.major
)

select * from final_assessment
order by overall_learning_growth desc, mastery_success_rate desc