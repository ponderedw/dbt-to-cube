{{ config(materialized='view') }}

with classroom_utilization as (
    select
        cs.room_id,
        cs.course_id,
        cs.semester_id,
        c.course_code,
        c.credits,
        sem.semester_name,
        sem.academic_year,
        count(distinct cs.session_date) as sessions_held,
        avg(cs.attendance_count) as avg_session_attendance,
        max(cs.attendance_count) as max_session_attendance,
        sum(cs.attendance_count) as total_student_sessions,
        extract(hour from cs.session_time) as session_hour,
        extract(dow from cs.session_date) as day_of_week
    from {{ ref('stg_class_sessions') }} cs
    inner join {{ ref('stg_courses') }} c on cs.course_id = c.course_id
    inner join {{ ref('stg_semesters') }} sem on cs.semester_id = sem.semester_id
    group by 
        cs.room_id, cs.course_id, cs.semester_id, c.course_code, c.credits,
        sem.semester_name, sem.academic_year, cs.session_time, cs.session_date
),

room_efficiency_metrics as (
    select
        room_id,
        semester_id,
        semester_name,
        count(distinct course_id) as courses_using_room,
        sum(sessions_held) as total_sessions_in_room,
        avg(avg_session_attendance) as room_avg_attendance,
        sum(total_student_sessions) as total_student_hours,
        count(distinct session_hour) as unique_time_slots_used,
        count(distinct day_of_week) as days_per_week_used,
        round(avg(avg_session_attendance / nullif(max_session_attendance, 0)) * 100, 2) as avg_capacity_utilization
    from classroom_utilization
    group by room_id, semester_id, semester_name
),

faculty_resource_allocation as (
    select
        f.faculty_id,
        f.full_name,
        f.position,
        f.salary,
        f.years_of_service,
        d.department_name,
        d.budget as department_budget,
        count(distinct cs.course_id) as courses_taught,
        count(distinct cs.semester_id) as semesters_active,
        sum(c.credits) as total_credit_hours_taught,
        count(distinct cs.session_date) as total_class_sessions,
        avg(cs.attendance_count) as avg_class_size,
        sum(cs.attendance_count) as total_student_contact_hours,
        round(f.salary / nullif(sum(cs.attendance_count), 0), 2) as cost_per_student_contact_hour,
        round(f.salary / nullif(sum(c.credits), 0), 2) as cost_per_credit_hour_taught
    from {{ ref('stg_faculty') }} f
    inner join {{ ref('stg_departments') }} d on f.department_id = d.department_id
    left join {{ ref('stg_class_sessions') }} cs on f.faculty_id = cs.faculty_id
    left join {{ ref('stg_courses') }} c on cs.course_id = c.course_id
    group by 
        f.faculty_id, f.full_name, f.position, f.salary, f.years_of_service,
        d.department_name, d.budget
),

technology_assignment_utilization as (
    select
        a.course_id,
        c.course_code,
        c.course_name,
        d.department_name,
        count(distinct a.assignment_id) as total_assignments,
        avg(ap.total_submissions) as avg_submissions_per_assignment,
        avg(ap.avg_percentage_score) as avg_assignment_performance,
        avg(ap.grading_completion_rate) as avg_grading_completion_rate,
        sum(ap.total_submissions) as total_submission_volume,
        count(case when a.assignment_category = 'Assessment' then 1 end) as assessment_assignments,
        count(case when a.assignment_category = 'Project' then 1 end) as project_assignments,
        count(case when a.assignment_category = 'Homework' then 1 end) as homework_assignments
    from {{ ref('stg_assignments') }} a
    inner join {{ ref('stg_courses') }} c on a.course_id = c.course_id
    inner join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('int_assignment_performance') }} ap on a.assignment_id = ap.assignment_id
    group by a.course_id, c.course_code, c.course_name, d.department_name
),

financial_resource_efficiency as (
    select
        d.department_id,
        d.department_name,
        d.budget,
        d.department_size,
        count(distinct f.faculty_id) as faculty_count,
        count(distinct s.student_id) as student_count,
        count(distinct c.course_id) as course_count,
        sum(f.salary) as total_faculty_costs,
        sum(tp.amount) as department_tuition_revenue,
        sum(fa.amount) as department_aid_disbursed,
        round(d.budget / nullif(count(distinct s.student_id), 0), 2) as budget_per_student,
        round(d.budget / nullif(count(distinct f.faculty_id), 0), 2) as budget_per_faculty,
        round(sum(tp.amount) / nullif(d.budget, 0), 2) as revenue_to_budget_ratio,
        round(sum(f.salary) / nullif(d.budget, 0) * 100, 2) as faculty_cost_percentage
    from {{ ref('stg_departments') }} d
    left join {{ ref('stg_faculty') }} f on d.department_id = f.department_id
    left join {{ ref('stg_students') }} s on d.department_id = s.major_id
    left join {{ ref('stg_courses') }} c on d.department_id = c.department_id
    left join {{ ref('stg_tuition_payments') }} tp on s.student_id = tp.student_id
    left join {{ ref('stg_financial_aid') }} fa on s.student_id = fa.student_id
    group by d.department_id, d.department_name, d.budget, d.department_size
),

resource_optimization_analysis as (
    select
        rem.room_id,
        rem.semester_name,
        rem.room_avg_attendance,
        rem.avg_capacity_utilization,
        rem.unique_time_slots_used,
        rem.days_per_week_used,
        case
            when rem.avg_capacity_utilization >= 85 then 'High Utilization'
            when rem.avg_capacity_utilization >= 65 then 'Good Utilization'
            when rem.avg_capacity_utilization >= 45 then 'Moderate Utilization'
            else 'Low Utilization'
        end as room_utilization_category,
        
        fra.faculty_id,
        fra.full_name,
        fra.department_name,
        fra.cost_per_student_contact_hour,
        fra.cost_per_credit_hour_taught,
        fra.total_credit_hours_taught,
        fra.total_student_contact_hours,
        case
            when fra.cost_per_student_contact_hour <= 50 then 'Highly Efficient'
            when fra.cost_per_student_contact_hour <= 100 then 'Efficient'
            when fra.cost_per_student_contact_hour <= 200 then 'Moderately Efficient'
            else 'Inefficient'
        end as faculty_efficiency_category,
        
        tau.course_id as tech_course_id,
        tau.total_submission_volume,
        tau.avg_grading_completion_rate,
        case
            when tau.avg_grading_completion_rate >= 95 then 'Excellent Assignment Management'
            when tau.avg_grading_completion_rate >= 85 then 'Good Assignment Management'
            when tau.avg_grading_completion_rate >= 70 then 'Fair Assignment Management'
            else 'Poor Assignment Management'
        end as assignment_management_category,
        
        fre.department_id as finance_dept_id,
        fre.revenue_to_budget_ratio,
        fre.faculty_cost_percentage,
        fre.budget_per_student,
        case
            when fre.revenue_to_budget_ratio >= 1.2 then 'Highly Profitable'
            when fre.revenue_to_budget_ratio >= 1.0 then 'Profitable'
            when fre.revenue_to_budget_ratio >= 0.8 then 'Break Even'
            else 'Loss Making'
        end as financial_efficiency_category
    from room_efficiency_metrics rem
    full outer join faculty_resource_allocation fra on 1=1  -- Cross join for analysis
    full outer join technology_assignment_utilization tau on 1=1
    full outer join financial_resource_efficiency fre on 1=1
),

comprehensive_utilization_score as (
    select
        coalesce(room_id, faculty_id, tech_course_id, finance_dept_id) as resource_identifier,
        'Multi-Resource Analysis' as resource_type,
        -- Room utilization score (0-25)
        case
            when avg_capacity_utilization >= 85 then 25
            when avg_capacity_utilization >= 65 then 20
            when avg_capacity_utilization >= 45 then 15
            else 10
        end as room_score,
        -- Faculty efficiency score (0-25)
        case
            when faculty_efficiency_category = 'Highly Efficient' then 25
            when faculty_efficiency_category = 'Efficient' then 20
            when faculty_efficiency_category = 'Moderately Efficient' then 15
            else 10
        end as faculty_score,
        -- Technology utilization score (0-25)
        case
            when assignment_management_category = 'Excellent Assignment Management' then 25
            when assignment_management_category = 'Good Assignment Management' then 20
            when assignment_management_category = 'Fair Assignment Management' then 15
            else 10
        end as technology_score,
        -- Financial efficiency score (0-25)
        case
            when financial_efficiency_category = 'Highly Profitable' then 25
            when financial_efficiency_category = 'Profitable' then 20
            when financial_efficiency_category = 'Break Even' then 15
            else 10
        end as financial_score,
        
        -- Overall utilization recommendations
        case
            when avg_capacity_utilization < 45 then 'Optimize room scheduling and capacity'
            when faculty_efficiency_category = 'Inefficient' then 'Review faculty workload and compensation'
            when assignment_management_category = 'Poor Assignment Management' then 'Improve assignment workflow processes'
            when financial_efficiency_category = 'Loss Making' then 'Critical financial restructuring needed'
            else 'Continue monitoring and minor optimizations'
        end as utilization_recommendation
    from resource_optimization_analysis
    where room_id is not null or faculty_id is not null or 
          tech_course_id is not null or finance_dept_id is not null
)

select 
    *,
    room_score + faculty_score + technology_score + financial_score as total_utilization_score
from comprehensive_utilization_score
order by total_utilization_score desc