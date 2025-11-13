{{ config(materialized='table') }}

with aid_impact as (
    select
        fa.student_id,
        s.full_name,
        s.gpa,
        s.academic_standing,
        s.student_status,
        s.years_enrolled,
        d.department_name,
        d.department_code,
        fa.aid_type,
        fa.aid_category,
        fa.amount as aid_amount,
        fa.academic_year,
        fa.support_level,
        fa.disbursement_period,
        eh.total_enrollments,
        eh.total_credits_earned,
        eh.avg_grade_points,
        eh.failed_courses_count,
        eh.withdrawn_courses_count,
        case when fa.student_id is not null then 1 else 0 end as receives_aid
    from {{ ref('stg_financial_aid') }} fa
    right join {{ ref('stg_students') }} s on fa.student_id = s.student_id
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join (
        select 
            student_id,
            max(total_enrollments) as total_enrollments,
            max(total_credits_earned) as total_credits_earned,
            max(avg_grade_points) as avg_grade_points,
            max(failed_courses_count) as failed_courses_count,
            max(withdrawn_courses_count) as withdrawn_courses_count
        from {{ ref('int_student_enrollment_history') }}
        group by student_id
    ) eh on s.student_id = eh.student_id
),

aid_summary as (
    select
        student_id,
        full_name,
        gpa,
        academic_standing,
        student_status,
        years_enrolled,
        department_name,
        department_code,
        total_enrollments,
        total_credits_earned,
        avg_grade_points,
        failed_courses_count,
        withdrawn_courses_count,
        sum(case when receives_aid = 1 then aid_amount else 0 end) as total_aid_received,
        count(case when receives_aid = 1 then 1 end) as aid_awards_count,
        max(case when aid_category = 'Merit-Based' then aid_amount else 0 end) as merit_aid,
        max(case when aid_category = 'Need-Based' then aid_amount else 0 end) as need_based_aid,
        max(case when aid_category = 'Loan' then aid_amount else 0 end) as loan_aid,
        max(case when aid_category = 'Work-Study' then aid_amount else 0 end) as work_study_aid,
        max(receives_aid) as receives_any_aid
    from aid_impact
    group by 
        student_id, full_name, gpa, academic_standing, student_status, 
        years_enrolled, department_name, department_code, total_enrollments, 
        total_credits_earned, avg_grade_points, failed_courses_count, withdrawn_courses_count
),

impact_analysis as (
    select
        *,
        case
            when receives_any_aid = 1 then 'Aid Recipient'
            else 'No Aid'
        end as aid_status,
        case
            when total_aid_received >= 15000 then 'High Aid'
            when total_aid_received >= 8000 then 'Moderate Aid'
            when total_aid_received >= 3000 then 'Low Aid'
            when total_aid_received > 0 then 'Minimal Aid'
            else 'No Aid'
        end as aid_level,
        case
            when merit_aid > need_based_aid and merit_aid > loan_aid then 'Merit Primary'
            when need_based_aid > loan_aid then 'Need Primary'
            when loan_aid > 0 then 'Loan Primary'
            else 'No Primary Type'
        end as primary_aid_type,
        round(total_aid_received / nullif(years_enrolled, 0), 2) as aid_per_year,
        case
            when gpa >= 3.5 and receives_any_aid = 1 then 'High Performing Aid Recipient'
            when gpa >= 3.0 and receives_any_aid = 1 then 'Good Performing Aid Recipient'
            when gpa < 3.0 and receives_any_aid = 1 then 'At-Risk Aid Recipient'
            when gpa >= 3.5 and receives_any_aid = 0 then 'High Performing No Aid'
            when gpa >= 3.0 and receives_any_aid = 0 then 'Good Performing No Aid'
            else 'At-Risk No Aid'
        end as performance_aid_category
    from aid_summary
),

departmental_aid_stats as (
    select
        department_name,
        count(*) as total_students_in_dept,
        count(case when receives_any_aid = 1 then 1 end) as aid_recipients_in_dept,
        avg(case when receives_any_aid = 1 then gpa end) as avg_gpa_aid_recipients,
        avg(case when receives_any_aid = 0 then gpa end) as avg_gpa_no_aid,
        avg(case when receives_any_aid = 1 then total_aid_received end) as avg_aid_amount,
        round(
            count(case when receives_any_aid = 1 then 1 end) * 100.0 / 
            nullif(count(*), 0), 2
        ) as aid_recipient_percentage
    from impact_analysis
    group by department_name
)

select 
    ia.*,
    das.aid_recipients_in_dept,
    das.avg_gpa_aid_recipients as dept_avg_gpa_aid_recipients,
    das.avg_gpa_no_aid as dept_avg_gpa_no_aid,
    das.avg_aid_amount as dept_avg_aid_amount,
    das.aid_recipient_percentage as dept_aid_percentage,
    case
        when das.avg_gpa_aid_recipients > das.avg_gpa_no_aid then 'Aid Recipients Outperform'
        when das.avg_gpa_aid_recipients < das.avg_gpa_no_aid then 'Non-Aid Recipients Outperform'
        else 'Similar Performance'
    end as dept_aid_performance_comparison
from impact_analysis ia
left join departmental_aid_stats das on ia.department_name = das.department_name