{{ config(materialized='view') }}

with student_baseline_metrics as (
    select
        s.student_id,
        s.full_name,
        s.age,
        s.gpa,
        s.years_enrolled,
        s.academic_standing,
        s.student_status,
        d.department_name,
        -- Early academic indicators (first semester performance)
        first_value(e.grade_points) over (partition by s.student_id order by sem.start_date) as first_semester_gpa,
        first_value(e.attendance_percentage) over (partition by s.student_id order by sem.start_date) as first_semester_attendance,
        first_value(c.difficulty_level) over (partition by s.student_id order by sem.start_date) as first_course_difficulty,
        -- Financial indicators
        fa.total_aid_received,
        fa.aid_recipient_category,
        tp.late_payment_rate,
        tp.payment_reliability,
        -- Engagement indicators
        eh.avg_attendance,
        eh.total_enrollments,
        eh.failed_courses_count,
        eh.withdrawn_courses_count,
        eh.total_credits_attempted,
        eh.total_credits_earned
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join {{ ref('stg_enrollments') }} e on s.student_id = e.student_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    left join (
        select 
            student_id,
            sum(total_aid_received) as total_aid_received,
            max(aid_recipient_category) as aid_recipient_category
        from {{ ref('student_financial_profile') }}
        group by student_id
    ) fa on s.student_id = fa.student_id
    left join (
        select 
            student_id,
            max(late_payment_rate) as late_payment_rate,
            max(payment_reliability) as payment_reliability
        from {{ ref('student_financial_profile') }}
        group by student_id
    ) tp on s.student_id = tp.student_id
    left join (
        select 
            student_id,
            max(avg_attendance) as avg_attendance,
            max(total_enrollments) as total_enrollments,
            max(failed_courses_count) as failed_courses_count,
            max(withdrawn_courses_count) as withdrawn_courses_count,
            max(total_credits_attempted) as total_credits_attempted,
            max(total_credits_earned) as total_credits_earned
        from {{ ref('int_student_enrollment_history') }}
        group by student_id
    ) eh on s.student_id = eh.student_id
),

predictive_features as (
    select
        sbm.*,
        -- Academic readiness indicators
        case when first_semester_gpa >= 3.5 then 1 else 0 end as strong_academic_start,
        case when first_semester_attendance >= 90 then 1 else 0 end as strong_engagement_start,
        case when first_course_difficulty <= 2 then 1 else 0 end as appropriate_starting_difficulty,
        
        -- Risk factors
        case when age > 25 then 1 else 0 end as non_traditional_age,
        case when total_aid_received > 15000 then 1 else 0 end as high_financial_need,
        case when late_payment_rate > 15 then 1 else 0 end as payment_issues,
        case when avg_attendance < 80 then 1 else 0 end as attendance_concern,
        case when failed_courses_count > 0 then 1 else 0 end as has_failed_courses,
        case when withdrawn_courses_count > 2 then 1 else 0 end as excessive_withdrawals,
        
        -- Protective factors
        case when aid_recipient_category like '%Merit%' then 1 else 0 end as merit_based_aid,
        case when payment_reliability = 'Excellent Payment History' then 1 else 0 end as reliable_payments,
        case when total_credits_earned >= years_enrolled * 15 then 1 else 0 end as on_track_credits,
        
        -- Calculated metrics
        round(total_credits_earned::numeric / nullif(total_credits_attempted, 0) * 100, 2) as completion_rate,
        round(total_credits_earned::numeric / nullif(years_enrolled, 0), 2) as credits_per_year,
        gpa - first_semester_gpa as gpa_trajectory,
        case
            when sbm.student_status = 'graduated' then 1
            when sbm.student_status = 'active' and sbm.gpa >= 2.0 then null  -- Still in progress
            else 0
        end as successful_outcome
    from student_baseline_metrics sbm
),

success_scoring as (
    select
        pf.*,
        -- Success probability score (0-100)
        round(
            (strong_academic_start * 15) +
            (strong_engagement_start * 10) +
            (appropriate_starting_difficulty * 5) +
            (merit_based_aid * 10) +
            (reliable_payments * 10) +
            (on_track_credits * 15) +
            (case when gpa >= 3.5 then 15
                  when gpa >= 3.0 then 12
                  when gpa >= 2.5 then 8
                  when gpa >= 2.0 then 5
                  else 0 end) +
            (case when completion_rate >= 95 then 10
                  when completion_rate >= 85 then 8
                  when completion_rate >= 75 then 6
                  else 3 end) -
            (non_traditional_age * 3) -
            (high_financial_need * 5) -
            (payment_issues * 8) -
            (attendance_concern * 12) -
            (has_failed_courses * 10) -
            (excessive_withdrawals * 15), 0
        ) as success_probability_score,
        
        -- Risk categories
        case
            when (non_traditional_age + high_financial_need + payment_issues + 
                  attendance_concern + has_failed_courses + excessive_withdrawals) >= 4 then 'Very High Risk'
            when (non_traditional_age + high_financial_need + payment_issues + 
                  attendance_concern + has_failed_courses + excessive_withdrawals) >= 3 then 'High Risk'
            when (non_traditional_age + high_financial_need + payment_issues + 
                  attendance_concern + has_failed_courses + excessive_withdrawals) >= 2 then 'Moderate Risk'
            when (non_traditional_age + high_financial_need + payment_issues + 
                  attendance_concern + has_failed_courses + excessive_withdrawals) = 1 then 'Low Risk'
            else 'Very Low Risk'
        end as overall_risk_category,
        
        -- Primary success factors
        case
            when strong_academic_start = 1 and strong_engagement_start = 1 then 'Strong Foundation'
            when reliable_payments = 1 and on_track_credits = 1 then 'Financial Stability'
            when merit_based_aid = 1 and gpa >= 3.5 then 'Academic Excellence'
            when completion_rate >= 90 and avg_attendance >= 85 then 'Consistent Performance'
            else 'Mixed Indicators'
        end as primary_success_factor,
        
        -- Primary risk factors
        case
            when attendance_concern = 1 and has_failed_courses = 1 then 'Academic Disengagement'
            when payment_issues = 1 and high_financial_need = 1 then 'Financial Stress'
            when excessive_withdrawals = 1 then 'Course Completion Issues'
            when non_traditional_age = 1 then 'Non-Traditional Challenges'
            else 'Standard Risk Profile'
        end as primary_risk_factor
    from predictive_features pf
),

intervention_recommendations as (
    select
        ss.*,
        -- Specific intervention recommendations
        case
            when overall_risk_category in ('Very High Risk', 'High Risk') and primary_risk_factor = 'Academic Disengagement' then
                'Immediate academic coaching, mandatory study sessions, attendance monitoring'
            when overall_risk_category in ('Very High Risk', 'High Risk') and primary_risk_factor = 'Financial Stress' then
                'Emergency financial aid, payment plan restructuring, financial literacy counseling'
            when overall_risk_category in ('Very High Risk', 'High Risk') and primary_risk_factor = 'Course Completion Issues' then
                'Academic planning review, prerequisite assessment, course load reduction'
            when overall_risk_category = 'Moderate Risk' then
                'Regular check-ins with advisor, peer tutoring, study skill workshops'
            when overall_risk_category = 'Low Risk' and primary_success_factor = 'Academic Excellence' then
                'Honors program recruitment, research opportunities, leadership roles'
            else 'Standard academic support services'
        end as recommended_interventions,
        
        -- Success prediction confidence
        case
            when years_enrolled >= 2 and total_enrollments >= 8 then 'High Confidence'
            when years_enrolled >= 1 and total_enrollments >= 4 then 'Moderate Confidence'
            else 'Low Confidence - Insufficient Data'
        end as prediction_confidence,
        
        -- Timeline for graduation prediction
        case
            when successful_outcome = 1 then 'Already Graduated'
            when success_probability_score >= 80 then 
                case
                    when credits_per_year >= 15 then 'Expected 4-year graduation'
                    when credits_per_year >= 12 then 'Expected 5-year graduation'
                    else 'Extended timeline likely'
                end
            when success_probability_score >= 60 then 'Likely to graduate with support'
            when success_probability_score >= 40 then 'At risk - intensive intervention needed'
            else 'Unlikely to graduate without major intervention'
        end as graduation_prediction
    from success_scoring ss
)

select * from intervention_recommendations
order by success_probability_score asc, overall_risk_category desc