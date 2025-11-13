{{ config(materialized='table') }}

with institutional_metrics as (
    select
        sem.semester_id,
        sem.semester_name,
        sem.academic_year,
        sem.semester_type,
        -- Enrollment metrics
        count(distinct e.student_id) as unique_students_enrolled,
        count(distinct e.enrollment_id) as total_course_enrollments,
        count(distinct e.course_id) as unique_courses_offered,
        count(distinct c.department_id) as departments_active,
        count(distinct f.faculty_id) as faculty_teaching,
        
        -- Academic performance metrics
        avg(e.grade_points) as institutional_avg_gpa,
        avg(e.attendance_percentage) as institutional_avg_attendance,
        count(case when e.grade_category = 'Excellent' then 1 end) as excellent_grades,
        count(case when e.grade_category in ('Excellent', 'Good', 'Satisfactory') then 1 end) as passing_grades,
        round(
            count(case when e.grade_category in ('Excellent', 'Good', 'Satisfactory') then 1 end) * 100.0 / 
            nullif(count(case when e.grade_category != 'Unknown' then 1 end), 0), 2
        ) as institutional_pass_rate,
        
        -- Student success indicators
        count(case when s.academic_standing = 'Dean''s List' then 1 end) as deans_list_students,
        count(case when s.academic_standing = 'Academic Probation' then 1 end) as students_on_probation,
        count(case when s.student_status = 'graduated' then 1 end) as graduates_this_period,
        
        -- Financial health
        sum(tp.amount) as total_tuition_revenue,
        sum(fa.amount) as total_financial_aid_disbursed,
        sum(f.salary) as total_faculty_compensation,
        
        -- Operational efficiency
        round(count(distinct e.enrollment_id)::numeric / nullif(count(distinct f.faculty_id), 0), 2) as enrollments_per_faculty,
        round(count(distinct e.student_id)::numeric / nullif(count(distinct f.faculty_id), 0), 2) as students_per_faculty,
        round(sum(tp.amount) / nullif(count(distinct e.student_id), 0), 2) as revenue_per_student
    from {{ ref('stg_semesters') }} sem
    left join {{ ref('stg_enrollments') }} e on sem.semester_id = e.semester_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_students') }} s on e.student_id = s.student_id
    left join {{ ref('stg_class_sessions') }} cs on c.course_id = cs.course_id and sem.semester_id = cs.semester_id
    left join {{ ref('stg_faculty') }} f on cs.faculty_id = f.faculty_id
    left join {{ ref('stg_tuition_payments') }} tp on s.student_id = tp.student_id and sem.semester_id = tp.semester_id
    left join {{ ref('stg_financial_aid') }} fa on s.student_id = fa.student_id
    group by sem.semester_id, sem.semester_name, sem.academic_year, sem.semester_type
),

performance_trends as (
    select
        im.*,
        lag(institutional_avg_gpa) over (order by semester_id) as prev_semester_gpa,
        lag(institutional_pass_rate) over (order by semester_id) as prev_semester_pass_rate,
        lag(unique_students_enrolled) over (order by semester_id) as prev_semester_enrollment,
        lag(total_tuition_revenue) over (order by semester_id) as prev_semester_revenue,
        
        -- Calculate trends
        institutional_avg_gpa - lag(institutional_avg_gpa) over (order by semester_id) as gpa_trend,
        institutional_pass_rate - lag(institutional_pass_rate) over (order by semester_id) as pass_rate_trend,
        unique_students_enrolled - lag(unique_students_enrolled) over (order by semester_id) as enrollment_trend,
        total_tuition_revenue - lag(total_tuition_revenue) over (order by semester_id) as revenue_trend,
        
        -- Calculate percentile rankings
        percent_rank() over (order by institutional_avg_gpa) as gpa_percentile,
        percent_rank() over (order by institutional_pass_rate) as pass_rate_percentile,
        percent_rank() over (order by unique_students_enrolled) as enrollment_percentile,
        percent_rank() over (order by revenue_per_student) as revenue_efficiency_percentile
    from institutional_metrics im
),

effectiveness_scoring as (
    select
        pt.*,
        -- Academic effectiveness score (0-100)
        round(
            (case when institutional_avg_gpa >= 3.0 then 25
                  when institutional_avg_gpa >= 2.5 then 20
                  when institutional_avg_gpa >= 2.0 then 15
                  else 10 end) +
            (case when institutional_pass_rate >= 85 then 25
                  when institutional_pass_rate >= 75 then 20
                  when institutional_pass_rate >= 65 then 15
                  else 10 end) +
            (case when institutional_avg_attendance >= 90 then 25
                  when institutional_avg_attendance >= 80 then 20
                  when institutional_avg_attendance >= 70 then 15
                  else 10 end) +
            (case when (deans_list_students::numeric / nullif(unique_students_enrolled, 0)) >= 0.15 then 25
                  when (deans_list_students::numeric / nullif(unique_students_enrolled, 0)) >= 0.10 then 20
                  when (deans_list_students::numeric / nullif(unique_students_enrolled, 0)) >= 0.05 then 15
                  else 10 end), 0
        ) as academic_effectiveness_score,
        
        -- Operational efficiency score (0-100)
        round(
            (case when students_per_faculty between 15 and 25 then 30
                  when students_per_faculty between 10 and 30 then 25
                  when students_per_faculty between 8 and 35 then 20
                  else 15 end) +
            (case when revenue_per_student >= 8000 then 25
                  when revenue_per_student >= 6000 then 20
                  when revenue_per_student >= 4000 then 15
                  else 10 end) +
            (case when (total_financial_aid_disbursed / nullif(total_tuition_revenue + total_financial_aid_disbursed, 0)) <= 0.3 then 25
                  when (total_financial_aid_disbursed / nullif(total_tuition_revenue + total_financial_aid_disbursed, 0)) <= 0.4 then 20
                  when (total_financial_aid_disbursed / nullif(total_tuition_revenue + total_financial_aid_disbursed, 0)) <= 0.5 then 15
                  else 10 end) +
            (case when (students_on_probation::numeric / nullif(unique_students_enrolled, 0)) <= 0.05 then 20
                  when (students_on_probation::numeric / nullif(unique_students_enrolled, 0)) <= 0.10 then 15
                  when (students_on_probation::numeric / nullif(unique_students_enrolled, 0)) <= 0.15 then 10
                  else 5 end), 0
        ) as operational_efficiency_score,
        
        -- Financial health score (0-100)
        round(
            (case when total_tuition_revenue > total_faculty_compensation * 1.5 then 40
                  when total_tuition_revenue > total_faculty_compensation * 1.2 then 30
                  when total_tuition_revenue > total_faculty_compensation then 20
                  else 10 end) +
            (case when revenue_trend > 0 then 30
                  when revenue_trend = 0 then 20
                  else 10 end) +
            (case when (total_financial_aid_disbursed / nullif(total_tuition_revenue, 0)) <= 0.4 then 30
                  when (total_financial_aid_disbursed / nullif(total_tuition_revenue, 0)) <= 0.6 then 20
                  else 10 end), 0
        ) as financial_health_score
    from performance_trends pt
),

comparative_analysis as (
    select
        es.*,
        -- Overall institutional effectiveness (weighted average)
        round(
            (academic_effectiveness_score * 0.4) + 
            (operational_efficiency_score * 0.3) + 
            (financial_health_score * 0.3), 1
        ) as overall_effectiveness_score,
        
        -- Trend categories
        case
            when gpa_trend > 0.1 then 'Improving Academic Performance'
            when gpa_trend < -0.1 then 'Declining Academic Performance'
            else 'Stable Academic Performance'
        end as academic_trend_category,
        
        case
            when enrollment_trend > 50 then 'Growing Enrollment'
            when enrollment_trend < -50 then 'Declining Enrollment'
            else 'Stable Enrollment'
        end as enrollment_trend_category,
        
        case
            when revenue_trend > 10000 then 'Growing Revenue'
            when revenue_trend < -10000 then 'Declining Revenue'
            else 'Stable Revenue'
        end as financial_trend_category,
        
        -- Performance categories
        case
            when academic_effectiveness_score >= 80 then 'High Academic Performance'
            when academic_effectiveness_score >= 65 then 'Good Academic Performance'
            when academic_effectiveness_score >= 50 then 'Fair Academic Performance'
            else 'Poor Academic Performance'
        end as academic_performance_category,
        
        case
            when operational_efficiency_score >= 80 then 'Highly Efficient'
            when operational_efficiency_score >= 65 then 'Efficient'
            when operational_efficiency_score >= 50 then 'Moderately Efficient'
            else 'Inefficient'
        end as operational_efficiency_category,
        
        case
            when financial_health_score >= 80 then 'Excellent Financial Health'
            when financial_health_score >= 65 then 'Good Financial Health'
            when financial_health_score >= 50 then 'Fair Financial Health'
            else 'Poor Financial Health'
        end as financial_health_category
    from effectiveness_scoring es
),

strategic_recommendations as (
    select
        ca.*,
        case
            when overall_effectiveness_score >= 80 then 'Maintain excellence and consider expansion opportunities'
            when academic_effectiveness_score < 50 then 'Focus on academic support and faculty development'
            when operational_efficiency_score < 50 then 'Review operational processes and resource allocation'
            when financial_health_score < 50 then 'Address financial sustainability and revenue diversification'
            when enrollment_trend_category = 'Declining Enrollment' then 'Implement enrollment growth strategies'
            else 'Continue current strategies with minor improvements'
        end as primary_strategic_recommendation,
        
        case
            when academic_trend_category = 'Declining Academic Performance' and 
                 operational_efficiency_category = 'Inefficient' then 'High Priority Action Required'
            when financial_health_category = 'Poor Financial Health' and
                 enrollment_trend_category = 'Declining Enrollment' then 'Critical Intervention Needed'
            when overall_effectiveness_score < 60 then 'Moderate Intervention Required'
            else 'Standard Monitoring'
        end as intervention_priority,
        
        -- Key performance indicators status
        case
            when institutional_pass_rate >= 80 and 
                 students_per_faculty between 15 and 25 and
                 revenue_per_student >= 6000 then 'All KPIs Met'
            when institutional_pass_rate < 70 or students_per_faculty > 30 or revenue_per_student < 4000 then 'Critical KPIs Not Met'
            else 'Some KPIs Need Attention'
        end as kpi_status
    from comparative_analysis ca
)

select * from strategic_recommendations
order by semester_id desc