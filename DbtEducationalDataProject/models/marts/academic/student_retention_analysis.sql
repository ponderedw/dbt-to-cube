{{ config(materialized='table') }}

with student_progression as (
    select
        s.student_id,
        s.full_name,
        s.email,
        s.enrollment_date,
        s.graduation_date,
        s.student_status,
        s.gpa,
        s.academic_standing,
        s.years_enrolled,
        s.age,
        d.department_name,
        d.department_code,
        eh.total_enrollments,
        eh.total_credits_attempted,
        eh.total_credits_earned,
        eh.failed_courses_count,
        eh.withdrawn_courses_count,
        eh.avg_grade_points,
        eh.avg_attendance,
        case
            when s.graduation_date is not null then 'Graduated'
            when s.student_status = 'dropped' then 'Dropped Out'
            when s.student_status = 'suspended' then 'Suspended'
            when s.student_status = 'active' then 'Currently Enrolled'
            else 'Other Status'
        end as retention_status,
        case
            when s.graduation_date is not null then 
                extract(year from s.graduation_date) - extract(year from s.enrollment_date)
            else 
                extract(year from current_date) - extract(year from s.enrollment_date)
        end as years_in_program,
        round(eh.total_credits_earned::numeric / nullif(eh.total_credits_attempted, 0) * 100, 2) as completion_rate
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
),

risk_analysis as (
    select
        *,
        case
            when retention_status = 'Graduated' then 0
            when gpa >= 3.5 and avg_attendance >= 90 and failed_courses_count = 0 then 1
            when gpa >= 3.0 and avg_attendance >= 80 and failed_courses_count <= 1 then 2
            when gpa >= 2.5 and avg_attendance >= 70 and failed_courses_count <= 2 then 3
            when gpa >= 2.0 and avg_attendance >= 60 and failed_courses_count <= 3 then 4
            else 5
        end as retention_risk_score,
        case
            when retention_status = 'Graduated' then 'Successful Completion'
            when gpa >= 3.5 and avg_attendance >= 90 and failed_courses_count = 0 then 'Excellent - No Risk'
            when gpa >= 3.0 and avg_attendance >= 80 and failed_courses_count <= 1 then 'Good - Low Risk'
            when gpa >= 2.5 and avg_attendance >= 70 and failed_courses_count <= 2 then 'Fair - Moderate Risk'
            when gpa >= 2.0 and avg_attendance >= 60 and failed_courses_count <= 3 then 'Poor - High Risk'
            else 'Critical - Very High Risk'
        end as risk_category,
        case
            when years_in_program <= 4 and retention_status in ('Currently Enrolled', 'Graduated') then 'On Track'
            when years_in_program between 5 and 6 and retention_status in ('Currently Enrolled', 'Graduated') then 'Extended Timeline'
            when years_in_program > 6 and retention_status = 'Currently Enrolled' then 'Significantly Delayed'
            when retention_status in ('Dropped Out', 'Suspended') then 'Did Not Complete'
            else 'Unknown'
        end as completion_timeline_status,
        case
            when completion_rate >= 95 then 'Excellent Progress'
            when completion_rate >= 85 then 'Good Progress'
            when completion_rate >= 75 then 'Fair Progress'
            when completion_rate >= 60 then 'Slow Progress'
            else 'Very Slow Progress'
        end as progress_category,
        case
            when withdrawn_courses_count = 0 then 'No Withdrawals'
            when withdrawn_courses_count = 1 then 'Minimal Withdrawals'
            when withdrawn_courses_count <= 3 then 'Some Withdrawals'
            else 'Many Withdrawals'
        end as withdrawal_pattern
    from student_progression
),

departmental_retention as (
    select
        department_name,
        count(*) as total_students,
        count(case when retention_status = 'Graduated' then 1 end) as graduated_students,
        count(case when retention_status = 'Currently Enrolled' then 1 end) as currently_enrolled,
        count(case when retention_status = 'Dropped Out' then 1 end) as dropped_students,
        count(case when retention_status = 'Suspended' then 1 end) as suspended_students,
        avg(case when retention_status = 'Graduated' then years_in_program end) as avg_graduation_time,
        avg(gpa) as dept_avg_gpa,
        avg(completion_rate) as dept_avg_completion_rate,
        round(
            count(case when retention_status = 'Graduated' then 1 end) * 100.0 / 
            nullif(count(case when retention_status in ('Graduated', 'Dropped Out', 'Suspended') then 1 end), 0), 2
        ) as graduation_rate,
        round(
            count(case when retention_status = 'Dropped Out' then 1 end) * 100.0 / 
            nullif(count(*), 0), 2
        ) as dropout_rate,
        round(
            count(case when risk_category like '%High Risk%' or risk_category like '%Critical%' then 1 end) * 100.0 / 
            nullif(count(case when retention_status = 'Currently Enrolled' then 1 end), 0), 2
        ) as at_risk_percentage
    from risk_analysis
    group by department_name
)

select 
    ra.*,
    dr.graduated_students as dept_graduated_students,
    dr.currently_enrolled as dept_currently_enrolled,
    dr.graduation_rate as dept_graduation_rate,
    dr.dropout_rate as dept_dropout_rate,
    dr.at_risk_percentage as dept_at_risk_percentage,
    dr.avg_graduation_time as dept_avg_graduation_time,
    dr.dept_avg_gpa,
    dr.dept_avg_completion_rate
from risk_analysis ra
left join departmental_retention dr on ra.department_name = dr.department_name