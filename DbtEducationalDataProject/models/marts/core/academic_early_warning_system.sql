{{ config(materialized='table') }}

with current_semester_performance as (
    select
        s.student_id,
        s.full_name,
        s.email,
        s.gpa as cumulative_gpa,
        s.academic_standing,
        s.years_enrolled,
        d.department_name,
        count(distinct e.enrollment_id) as current_enrollments,
        avg(e.grade_points) as current_semester_gpa,
        avg(e.attendance_percentage) as current_attendance,
        count(case when e.grade_points < 2.0 then 1 end) as failing_courses,
        count(case when e.attendance_percentage < 70 then 1 end) as low_attendance_courses,
        min(e.grade_points) as lowest_current_grade,
        min(e.attendance_percentage) as lowest_attendance,
        string_agg(c.course_code, ', ' order by e.grade_points asc) as struggling_courses
    from {{ ref('stg_students') }} s
    inner join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join {{ ref('stg_enrollments') }} e on s.student_id = e.student_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    where sem.is_current = true 
      and s.student_status = 'active'
      and e.enrollment_status in ('In Progress', 'Completed')
    group by 
        s.student_id, s.full_name, s.email, s.gpa, s.academic_standing, 
        s.years_enrolled, d.department_name
),

historical_patterns as (
    select
        student_id,
        count(distinct e.semester_id) as total_semesters,
        avg(grade_points) as historical_avg_gpa,
        count(case when grade_points < 2.0 then 1 end) as total_failed_courses,
        count(case when enrollment_status = 'Withdrawn' then 1 end) as total_withdrawals,
        min(grade_points) as worst_historical_grade,
        stddev(grade_points) as grade_consistency,
        lag(avg(grade_points)) over (partition by student_id order by e.semester_id desc) as previous_semester_gpa
    from {{ ref('stg_enrollments') }} e
    inner join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    where sem.is_current = false
    group by student_id, e.semester_id
),

assignment_performance_indicators as (
    select
        e.student_id,
        count(distinct asub.assignment_id) as assignments_completed,
        avg(asub.score / nullif(a.max_points, 0) * 100) as avg_assignment_percentage,
        count(case when asub.late_submission then 1 end) as late_submissions,
        count(case when asub.score / nullif(a.max_points, 0) < 0.6 then 1 end) as poor_assignment_scores,
        round(
            count(case when asub.late_submission then 1 end) * 100.0 / 
            nullif(count(distinct asub.assignment_id), 0), 2
        ) as late_submission_rate
    from {{ ref('stg_enrollments') }} e
    inner join {{ ref('stg_assignments') }} a on e.course_id = a.course_id and e.semester_id = a.semester_id
    inner join {{ ref('stg_assignment_submissions') }} asub on a.assignment_id = asub.assignment_id and e.student_id = asub.student_id
    inner join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    where sem.is_current = true
    group by e.student_id
),

financial_stress_indicators as (
    select
        student_id,
        max(case when late_payment_rate > 25 then 1 else 0 end) as has_payment_issues,
        max(case when total_aid_received = 0 then 1 else 0 end) as no_financial_aid,
        max(case when payment_reliability = 'Poor Payment History' then 1 else 0 end) as poor_payment_history
    from {{ ref('student_financial_profile') }}
    group by student_id
),

early_warning_indicators as (
    select
        csp.student_id,
        csp.full_name,
        csp.email,
        csp.department_name,
        csp.cumulative_gpa,
        csp.current_semester_gpa,
        csp.current_attendance,
        csp.failing_courses,
        csp.low_attendance_courses,
        csp.struggling_courses,
        hp.historical_avg_gpa,
        hp.total_failed_courses,
        hp.total_withdrawals,
        hp.grade_consistency,
        hp.previous_semester_gpa,
        api.avg_assignment_percentage,
        api.late_submission_rate,
        api.poor_assignment_scores,
        fsi.has_payment_issues,
        fsi.no_financial_aid,
        fsi.poor_payment_history,
        
        -- Academic warning flags
        case when csp.current_semester_gpa < 2.0 then 1 else 0 end as academic_failure_flag,
        case when csp.current_attendance < 75 then 1 else 0 end as attendance_warning_flag,
        case when csp.failing_courses >= 2 then 1 else 0 end as multiple_failures_flag,
        case when csp.current_semester_gpa < csp.cumulative_gpa - 0.5 then 1 else 0 end as declining_performance_flag,
        case when api.late_submission_rate > 30 then 1 else 0 end as assignment_issues_flag,
        
        -- Engagement warning flags
        case when csp.low_attendance_courses >= 3 then 1 else 0 end as disengagement_flag,
        case when api.avg_assignment_percentage < 65 then 1 else 0 end as poor_assignment_flag,
        case when hp.grade_consistency > 1.5 then 1 else 0 end as inconsistent_performance_flag,
        
        -- Financial warning flags
        case when fsi.has_payment_issues = 1 then 1 else 0 end as financial_stress_flag,
        
        -- Historical pattern flags
        case when hp.total_failed_courses >= 3 then 1 else 0 end as chronic_failure_flag,
        case when hp.total_withdrawals >= 2 then 1 else 0 end as withdrawal_pattern_flag
    from current_semester_performance csp
    left join (
        select 
            student_id,
            avg(historical_avg_gpa) as historical_avg_gpa,
            sum(total_failed_courses) as total_failed_courses,
            sum(total_withdrawals) as total_withdrawals,
            avg(grade_consistency) as grade_consistency,
            max(previous_semester_gpa) as previous_semester_gpa
        from historical_patterns
        group by student_id
    ) hp on csp.student_id = hp.student_id
    left join assignment_performance_indicators api on csp.student_id = api.student_id
    left join financial_stress_indicators fsi on csp.student_id = fsi.student_id
),

risk_scoring as (
    select
        ewi.*,
        -- Calculate overall risk score
        academic_failure_flag + attendance_warning_flag + multiple_failures_flag + 
        declining_performance_flag + assignment_issues_flag + disengagement_flag + 
        poor_assignment_flag + inconsistent_performance_flag + financial_stress_flag + 
        chronic_failure_flag + withdrawal_pattern_flag as total_warning_flags,
        
        -- Risk level classification
        case
            when (academic_failure_flag + attendance_warning_flag + multiple_failures_flag + 
                  declining_performance_flag + assignment_issues_flag + disengagement_flag + 
                  poor_assignment_flag + inconsistent_performance_flag + financial_stress_flag + 
                  chronic_failure_flag + withdrawal_pattern_flag) >= 7 then 'Critical Risk'
            when (academic_failure_flag + attendance_warning_flag + multiple_failures_flag + 
                  declining_performance_flag + assignment_issues_flag + disengagement_flag + 
                  poor_assignment_flag + inconsistent_performance_flag + financial_stress_flag + 
                  chronic_failure_flag + withdrawal_pattern_flag) >= 5 then 'High Risk'
            when (academic_failure_flag + attendance_warning_flag + multiple_failures_flag + 
                  declining_performance_flag + assignment_issues_flag + disengagement_flag + 
                  poor_assignment_flag + inconsistent_performance_flag + financial_stress_flag + 
                  chronic_failure_flag + withdrawal_pattern_flag) >= 3 then 'Moderate Risk'
            when (academic_failure_flag + attendance_warning_flag + multiple_failures_flag + 
                  declining_performance_flag + assignment_issues_flag + disengagement_flag + 
                  poor_assignment_flag + inconsistent_performance_flag + financial_stress_flag + 
                  chronic_failure_flag + withdrawal_pattern_flag) >= 1 then 'Low Risk'
            else 'No Risk'
        end as risk_level,
        
        -- Primary risk category
        case
            when academic_failure_flag = 1 or multiple_failures_flag = 1 then 'Academic Crisis'
            when attendance_warning_flag = 1 or disengagement_flag = 1 then 'Engagement Issues'
            when financial_stress_flag = 1 then 'Financial Difficulties'
            when declining_performance_flag = 1 or inconsistent_performance_flag = 1 then 'Performance Decline'
            when chronic_failure_flag = 1 or withdrawal_pattern_flag = 1 then 'Chronic Issues'
            else 'General Risk'
        end as primary_risk_category
    from early_warning_indicators ewi
),

intervention_planning as (
    select
        rs.*,
        -- Immediate interventions
        case
            when risk_level = 'Critical Risk' then 'URGENT: Schedule immediate meeting with academic advisor, dean, and counselor'
            when risk_level = 'High Risk' and primary_risk_category = 'Academic Crisis' then 'Schedule tutoring, reduce course load, academic probation review'
            when risk_level = 'High Risk' and primary_risk_category = 'Engagement Issues' then 'Mandatory attendance tracking, peer mentorship program'
            when risk_level = 'High Risk' and primary_risk_category = 'Financial Difficulties' then 'Financial aid counseling, emergency assistance application'
            when risk_level = 'Moderate Risk' then 'Proactive check-in with advisor, study skills workshop'
            when risk_level = 'Low Risk' then 'Monitor progress, optional support services'
            else 'Standard academic support'
        end as recommended_immediate_intervention,
        
        -- Follow-up timeline
        case
            when risk_level = 'Critical Risk' then 'Daily check-ins for 2 weeks, then weekly'
            when risk_level = 'High Risk' then 'Weekly check-ins for 1 month'
            when risk_level = 'Moderate Risk' then 'Bi-weekly check-ins'
            when risk_level = 'Low Risk' then 'Monthly check-ins'
            else 'Semester check-ins'
        end as follow_up_schedule,
        
        -- Success probability
        case
            when risk_level = 'Critical Risk' then 'Low - Requires intensive intervention'
            when risk_level = 'High Risk' and chronic_failure_flag = 0 then 'Moderate - Good chance with proper support'
            when risk_level = 'High Risk' then 'Low-Moderate - Pattern of difficulties'
            when risk_level = 'Moderate Risk' then 'Good - Early intervention effective'
            else 'Excellent - Minor adjustments needed'
        end as success_probability_with_intervention,
        
        -- Alert priority for staff
        case
            when risk_level = 'Critical Risk' then 1
            when risk_level = 'High Risk' then 2
            when risk_level = 'Moderate Risk' then 3
            else 4
        end as alert_priority,
        
        current_timestamp as alert_generated_timestamp
    from risk_scoring rs
)

select * from intervention_planning
where risk_level != 'No Risk'
order by alert_priority asc, total_warning_flags desc, current_semester_gpa asc