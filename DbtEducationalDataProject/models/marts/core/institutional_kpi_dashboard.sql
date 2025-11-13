{{ config(materialized='table') }}

with enrollment_kpis as (
    select
        current_date as report_date,
        'Enrollment Metrics' as kpi_category,
        count(distinct s.student_id) as total_active_students,
        count(distinct case when s.student_status = 'active' then s.student_id end) as currently_enrolled_students,
        count(distinct case when s.student_status = 'graduated' then s.student_id end) as total_graduates,
        count(distinct e.enrollment_id) as total_course_enrollments,
        round(avg(s.gpa), 2) as institutional_avg_gpa,
        round(
            count(distinct case when s.student_status = 'graduated' then s.student_id end) * 100.0 / 
            nullif(count(distinct s.student_id), 0), 2
        ) as overall_graduation_rate,
        round(
            count(distinct case when s.academic_standing = 'Dean''s List' then s.student_id end) * 100.0 / 
            nullif(count(distinct case when s.student_status = 'active' then s.student_id end), 0), 2
        ) as honors_student_percentage,
        round(
            count(distinct case when s.student_status = 'dropped' then s.student_id end) * 100.0 / 
            nullif(count(distinct s.student_id), 0), 2
        ) as dropout_rate
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_enrollments') }} e on s.student_id = e.student_id
),

academic_performance_kpis as (
    select
        current_date as report_date,
        'Academic Performance' as kpi_category,
        round(avg(e.grade_points), 2) as avg_course_performance,
        round(avg(e.attendance_percentage), 2) as avg_student_attendance,
        round(
            count(case when e.grade_category in ('Excellent', 'Good', 'Satisfactory') then 1 end) * 100.0 / 
            nullif(count(case when e.grade_category != 'Unknown' then 1 end), 0), 2
        ) as course_success_rate,
        round(
            count(case when e.enrollment_status = 'Withdrawn' then 1 end) * 100.0 / 
            nullif(count(e.enrollment_id), 0), 2
        ) as course_withdrawal_rate,
        count(distinct c.course_id) as total_courses_offered,
        round(avg(c.difficulty_level), 1) as avg_course_difficulty,
        count(case when c.difficulty_level >= 4 then 1 end) as advanced_courses_offered
    from {{ ref('stg_enrollments') }} e
    inner join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    inner join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
),

faculty_kpis as (
    select
        current_date as report_date,
        'Faculty Metrics' as kpi_category,
        count(distinct f.faculty_id) as total_faculty,
        round(avg(f.salary), 0) as avg_faculty_salary,
        round(avg(f.years_of_service), 1) as avg_years_of_service,
        count(case when f.position = 'Professor' then 1 end) as full_professors,
        count(case when f.position = 'Associate Professor' then 1 end) as associate_professors,
        count(case when f.position = 'Assistant Professor' then 1 end) as assistant_professors,
        round(
            count(case when f.position = 'Professor' then 1 end) * 100.0 / 
            nullif(count(f.faculty_id), 0), 2
        ) as senior_faculty_percentage,
        round(
            count(distinct s.student_id) / nullif(count(distinct f.faculty_id), 0), 2
        ) as student_faculty_ratio
    from {{ ref('stg_faculty') }} f
    left join {{ ref('stg_class_sessions') }} cs on f.faculty_id = cs.faculty_id
    left join {{ ref('stg_enrollments') }} e on cs.course_id = e.course_id and cs.semester_id = e.semester_id
    left join {{ ref('stg_students') }} s on e.student_id = s.student_id
),

financial_kpis as (
    select
        current_date as report_date,
        'Financial Metrics' as kpi_category,
        sum(tp.amount) as total_tuition_revenue,
        sum(fa.amount) as total_financial_aid,
        sum(d.budget) as total_departmental_budgets,
        sum(f.salary) as total_faculty_compensation,
        round(sum(tp.amount) / nullif(count(distinct s.student_id), 0), 2) as revenue_per_student,
        round(sum(d.budget) / nullif(count(distinct s.student_id), 0), 2) as cost_per_student,
        round(sum(tp.amount) / nullif(sum(d.budget), 0), 2) as revenue_to_budget_ratio,
        round(sum(f.salary) / nullif(sum(d.budget), 0) * 100, 2) as faculty_cost_percentage,
        round(
            sum(fa.amount) * 100.0 / nullif(sum(tp.amount) + sum(fa.amount), 0), 2
        ) as financial_aid_percentage
    from {{ ref('stg_tuition_payments') }} tp
    full outer join {{ ref('stg_financial_aid') }} fa on tp.student_id = fa.student_id
    full outer join {{ ref('stg_students') }} s on coalesce(tp.student_id, fa.student_id) = s.student_id
    full outer join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    full outer join {{ ref('stg_faculty') }} f on d.department_id = f.department_id
),

operational_kpis as (
    select
        current_date as report_date,
        'Operational Metrics' as kpi_category,
        count(distinct d.department_id) as total_departments,
        count(distinct cs.room_id) as total_classrooms_used,
        count(distinct cs.session_date) as total_class_sessions,
        round(avg(cs.attendance_count), 1) as avg_class_attendance,
        count(distinct a.assignment_id) as total_assignments_given,
        round(avg(ap.avg_percentage_score), 1) as avg_assignment_performance,
        round(avg(ap.late_submission_rate), 1) as avg_late_submission_rate,
        count(distinct sem.semester_id) as semesters_tracked
    from {{ ref('stg_departments') }} d
    left join {{ ref('stg_class_sessions') }} cs on 1=1
    left join {{ ref('stg_assignments') }} a on 1=1
    left join {{ ref('int_assignment_performance') }} ap on a.assignment_id = ap.assignment_id
    left join {{ ref('stg_semesters') }} sem on 1=1
),

semester_stats as (
    select
        sem.semester_id,
        sem.semester_name,
        sem.start_date,
        count(distinct e.student_id) as semester_students,
        round(avg(e.grade_points)::numeric, 2) as semester_gpa
    from {{ ref('stg_semesters') }} sem
    left join {{ ref('stg_enrollments') }} e on sem.semester_id = e.semester_id
    group by sem.semester_id, sem.semester_name, sem.start_date
),

semester_trends as (
    select
        current_date as report_date,
        'Trend Analysis' as kpi_category,
        current_sem.semester_name as current_semester,
        prev_sem.semester_name as previous_semester,
        current_sem.semester_students as current_semester_students,
        prev_sem.semester_students as previous_semester_students,
        current_sem.semester_gpa as current_semester_gpa,
        prev_sem.semester_gpa as previous_semester_gpa,
        round(
            (current_sem.semester_students - prev_sem.semester_students) * 100.0 /
            nullif(prev_sem.semester_students, 0)::numeric, 2
        ) as enrollment_growth_rate,
        round(
            (current_sem.semester_gpa - prev_sem.semester_gpa)::numeric, 2
        ) as gpa_change
    from semester_stats current_sem
    left join semester_stats prev_sem on prev_sem.start_date = (
        select max(start_date) 
        from semester_stats 
        where start_date < current_sem.start_date
    )
    where current_sem.start_date = (select max(start_date) from semester_stats)
),

kpi_targets_and_status as (
    select
        ekpi.report_date,
        ekpi.kpi_category,
        'Total Active Students' as kpi_name,
        ekpi.total_active_students as actual_value,
        1200 as target_value,  -- Example target
        case 
            when ekpi.total_active_students >= 1200 then 'On Target'
            when ekpi.total_active_students >= 1080 then 'Close to Target' 
            else 'Below Target'
        end as status,
        round((ekpi.total_active_students / 1200.0) * 100, 1) as achievement_percentage
    from enrollment_kpis ekpi
    
    union all
    
    select
        akpi.report_date,
        akpi.kpi_category,
        'Course Success Rate' as kpi_name,
        akpi.course_success_rate as actual_value,
        85.0 as target_value,
        case 
            when akpi.course_success_rate >= 85 then 'On Target'
            when akpi.course_success_rate >= 76.5 then 'Close to Target'
            else 'Below Target'
        end as status,
        round((akpi.course_success_rate / 85.0) * 100, 1) as achievement_percentage
    from academic_performance_kpis akpi
    
    union all
    
    select
        fkpi.report_date,
        fkpi.kpi_category,
        'Student Faculty Ratio' as kpi_name,
        fkpi.student_faculty_ratio as actual_value,
        20.0 as target_value,
        case 
            when fkpi.student_faculty_ratio between 15 and 25 then 'On Target'
            when fkpi.student_faculty_ratio between 12 and 28 then 'Close to Target'
            else 'Below Target'
        end as status,
        case 
            when fkpi.student_faculty_ratio between 15 and 25 then 100.0
            else round((20.0 / abs(fkpi.student_faculty_ratio - 20.0)) * 100, 1)
        end as achievement_percentage
    from faculty_kpis fkpi
    
    union all
    
    select
        fikpi.report_date,
        fikpi.kpi_category,
        'Revenue to Budget Ratio' as kpi_name,
        fikpi.revenue_to_budget_ratio as actual_value,
        1.2 as target_value,
        case 
            when fikpi.revenue_to_budget_ratio >= 1.2 then 'On Target'
            when fikpi.revenue_to_budget_ratio >= 1.08 then 'Close to Target'
            else 'Below Target'
        end as status,
        round((fikpi.revenue_to_budget_ratio / 1.2) * 100, 1) as achievement_percentage
    from financial_kpis fikpi
),

executive_dashboard_summary as (
    select
        current_date as dashboard_date,
        count(*) as total_kpis_tracked,
        count(case when status = 'On Target' then 1 end) as kpis_on_target,
        count(case when status = 'Close to Target' then 1 end) as kpis_close_to_target,
        count(case when status = 'Below Target' then 1 end) as kpis_below_target,
        round(
            count(case when status = 'On Target' then 1 end) * 100.0 / count(*), 1
        ) as overall_kpi_success_rate,
        round(avg(achievement_percentage), 1) as avg_achievement_percentage,
        case
            when count(case when status = 'Below Target' then 1 end) >= 3 then 'Critical - Multiple KPIs Below Target'
            when count(case when status = 'Below Target' then 1 end) >= 2 then 'Warning - Some KPIs Below Target'
            when count(case when status = 'On Target' then 1 end) >= count(*) * 0.8 then 'Excellent - Most KPIs On Target'
            else 'Good - Majority of KPIs Performing Well'
        end as overall_institutional_health
    from kpi_targets_and_status
)

-- Final comprehensive KPI dashboard
select
    kts.*,
    eds.overall_kpi_success_rate,
    eds.overall_institutional_health,
    case
        when kts.status = 'Below Target' and kts.kpi_name in ('Course Success Rate', 'Student Faculty Ratio') then 'High Priority Action Required'
        when kts.status = 'Below Target' then 'Action Required'
        when kts.status = 'Close to Target' then 'Monitor Closely'
        else 'Continue Current Strategy'
    end as action_priority,
    case
        when kts.kpi_name = 'Total Active Students' and kts.status = 'Below Target' then 'Enhance recruitment and retention programs'
        when kts.kpi_name = 'Course Success Rate' and kts.status = 'Below Target' then 'Improve academic support and teaching effectiveness'
        when kts.kpi_name = 'Student Faculty Ratio' and kts.status = 'Below Target' then 'Optimize faculty allocation or adjust enrollment'
        when kts.kpi_name = 'Revenue to Budget Ratio' and kts.status = 'Below Target' then 'Review pricing strategy and cost management'
        else 'Maintain current practices'
    end as improvement_recommendation
from kpi_targets_and_status kts
cross join executive_dashboard_summary eds
order by 
    case when kts.status = 'Below Target' then 1
         when kts.status = 'Close to Target' then 2
         else 3 end,
    kts.achievement_percentage asc