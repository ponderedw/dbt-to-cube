{{ config(materialized='view') }}

with risk_indicators as (
    select
        s.student_id,
        s.full_name,
        s.email,
        s.gpa,
        s.academic_standing,
        s.student_status,
        s.years_enrolled,
        d.department_name,
        eh.total_enrollments,
        eh.total_credits_attempted,
        eh.total_credits_earned,
        eh.failed_courses_count,
        eh.withdrawn_courses_count,
        eh.avg_grade_points,
        eh.avg_attendance,
        sfp.total_aid_received,
        sfp.late_payment_rate,
        sfp.payment_reliability,
        case when eh.avg_attendance < 75 then 1 else 0 end as low_attendance_flag,
        case when s.gpa < 2.0 then 1 else 0 end as academic_probation_flag,
        case when eh.failed_courses_count >= 2 then 1 else 0 end as multiple_failures_flag,
        case when eh.withdrawn_courses_count >= 3 then 1 else 0 end as excessive_withdrawals_flag,
        case when sfp.late_payment_rate > 25 then 1 else 0 end as payment_issues_flag,
        case when s.years_enrolled > 5 and s.student_status = 'active' then 1 else 0 end as extended_timeline_flag,
        case when eh.total_credits_earned < (s.years_enrolled * 12) then 1 else 0 end as slow_progress_flag,
        case when sfp.total_aid_received = 0 and sfp.late_payment_rate > 10 then 1 else 0 end as financial_stress_flag
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join (
        select 
            student_id,
            max(total_enrollments) as total_enrollments,
            max(total_credits_attempted) as total_credits_attempted,
            max(total_credits_earned) as total_credits_earned,
            max(failed_courses_count) as failed_courses_count,
            max(withdrawn_courses_count) as withdrawn_courses_count,
            max(avg_grade_points) as avg_grade_points,
            max(avg_attendance) as avg_attendance
        from {{ ref('int_student_enrollment_history') }}
        group by student_id
    ) eh on s.student_id = eh.student_id
    left join {{ ref('student_financial_profile') }} sfp on s.student_id = sfp.student_id
),

risk_scoring as (
    select
        *,
        low_attendance_flag + academic_probation_flag + multiple_failures_flag + 
        excessive_withdrawals_flag + payment_issues_flag + extended_timeline_flag + 
        slow_progress_flag + financial_stress_flag as total_risk_score,
        case
            when (low_attendance_flag + academic_probation_flag + multiple_failures_flag + 
                  excessive_withdrawals_flag + payment_issues_flag + extended_timeline_flag + 
                  slow_progress_flag + financial_stress_flag) >= 5 then 'Critical Risk'
            when (low_attendance_flag + academic_probation_flag + multiple_failures_flag + 
                  excessive_withdrawals_flag + payment_issues_flag + extended_timeline_flag + 
                  slow_progress_flag + financial_stress_flag) >= 3 then 'High Risk'
            when (low_attendance_flag + academic_probation_flag + multiple_failures_flag + 
                  excessive_withdrawals_flag + payment_issues_flag + extended_timeline_flag + 
                  slow_progress_flag + financial_stress_flag) >= 1 then 'Moderate Risk'
            else 'Low Risk'
        end as risk_level,
        case
            when academic_probation_flag = 1 and multiple_failures_flag = 1 then 'Academic Crisis'
            when low_attendance_flag = 1 and slow_progress_flag = 1 then 'Engagement Issues'
            when payment_issues_flag = 1 and financial_stress_flag = 1 then 'Financial Crisis'
            when excessive_withdrawals_flag = 1 and extended_timeline_flag = 1 then 'Completion Risk'
            else 'General Risk'
        end as primary_risk_category
    from risk_indicators
),

intervention_recommendations as (
    select
        *,
        case
            when risk_level = 'Critical Risk' then 'Immediate intervention required - Academic advisor meeting, counseling referral, financial aid review'
            when risk_level = 'High Risk' and primary_risk_category = 'Academic Crisis' then 'Academic support - Tutoring, study skills workshop, course load reduction'
            when risk_level = 'High Risk' and primary_risk_category = 'Financial Crisis' then 'Financial counseling - Payment plan setup, additional aid application assistance'
            when risk_level = 'High Risk' and primary_risk_category = 'Engagement Issues' then 'Engagement support - Attendance monitoring, study group placement, mentor assignment'
            when risk_level = 'Moderate Risk' then 'Preventive support - Regular check-ins, academic planning session'
            else 'Standard support - Routine academic advising'
        end as recommended_intervention,
        case
            when low_attendance_flag = 1 then 'Monitor attendance closely'
            else ''
        end || case
            when academic_probation_flag = 1 then ' | Academic probation follow-up'
            else ''
        end || case
            when payment_issues_flag = 1 then ' | Financial aid counseling'
            else ''
        end || case
            when slow_progress_flag = 1 then ' | Degree planning review'
            else ''
        end as specific_action_items
    from risk_scoring
)

select * from intervention_recommendations