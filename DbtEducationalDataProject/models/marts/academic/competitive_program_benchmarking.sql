{{ config(materialized='table') }}

with program_performance_metrics as (
    select
        d.department_name as program_name,
        d.department_code,
        d.budget,
        d.department_size,
        count(distinct s.student_id) as total_students,
        count(distinct f.faculty_id) as faculty_count,
        count(distinct c.course_id) as course_offerings,
        avg(s.gpa) as program_avg_gpa,
        count(case when s.student_status = 'graduated' then 1 end) as graduates,
        count(case when s.academic_standing = 'Dean''s List' then 1 end) as honors_students,
        avg(e.attendance_percentage) as avg_student_engagement,
        round(
            count(case when s.student_status = 'graduated' then 1 end) * 100.0 / 
            nullif(count(distinct s.student_id), 0), 2
        ) as graduation_rate,
        round(
            count(case when s.academic_standing = 'Dean''s List' then 1 end) * 100.0 / 
            nullif(count(distinct s.student_id), 0), 2
        ) as honors_percentage,
        round(
            count(case when s.student_status = 'dropped' then 1 end) * 100.0 / 
            nullif(count(distinct s.student_id), 0), 2
        ) as dropout_rate
    from {{ ref('stg_departments') }} d
    left join {{ ref('stg_students') }} s on d.department_id = s.major_id
    left join {{ ref('stg_faculty') }} f on d.department_id = f.department_id
    left join {{ ref('stg_courses') }} c on d.department_id = c.department_id
    left join {{ ref('stg_enrollments') }} e on s.student_id = e.student_id and c.course_id = e.course_id
    group by d.department_name, d.department_code, d.budget, d.department_size
),

financial_performance_metrics as (
    select
        d.department_name,
        sum(tp.amount) as total_revenue,
        sum(fa.amount) as aid_disbursed,
        sum(f.salary) as faculty_costs,
        round(sum(tp.amount) / nullif(count(distinct s.student_id), 0), 2) as revenue_per_student,
        round(d.budget / nullif(count(distinct s.student_id), 0), 2) as cost_per_student,
        round(sum(tp.amount) / nullif(d.budget, 0), 2) as revenue_efficiency_ratio,
        round(sum(f.salary) / nullif(d.budget, 0) * 100, 2) as faculty_cost_ratio
    from {{ ref('stg_departments') }} d
    left join {{ ref('stg_students') }} s on d.department_id = s.major_id
    left join {{ ref('stg_tuition_payments') }} tp on s.student_id = tp.student_id
    left join {{ ref('stg_financial_aid') }} fa on s.student_id = fa.student_id
    left join {{ ref('stg_faculty') }} f on d.department_id = f.department_id
    group by d.department_name, d.budget
),

faculty_quality_metrics as (
    select
        d.department_name,
        avg(f.years_of_service) as avg_faculty_experience,
        count(case when f.position = 'Professor' then 1 end) as senior_faculty_count,
        round(
            count(case when f.position = 'Professor' then 1 end) * 100.0 / 
            nullif(count(distinct f.faculty_id), 0), 2
        ) as senior_faculty_percentage,
        avg(f.salary) as avg_faculty_compensation,
        round(count(distinct s.student_id) / nullif(count(distinct f.faculty_id), 0), 2) as student_faculty_ratio
    from {{ ref('stg_departments') }} d
    left join {{ ref('stg_faculty') }} f on d.department_id = f.department_id
    left join {{ ref('stg_students') }} s on d.department_id = s.major_id
    group by d.department_name
),

course_quality_metrics as (
    select
        d.department_name,
        avg(c.difficulty_level) as avg_course_rigor,
        count(case when c.difficulty_level >= 4 then 1 end) as advanced_courses,
        round(
            count(case when c.difficulty_level >= 4 then 1 end) * 100.0 / 
            nullif(count(distinct c.course_id), 0), 2
        ) as advanced_course_percentage,
        avg(cpm.pass_rate) as avg_course_success_rate,
        avg(cpm.avg_grade_points) as avg_course_gpa
    from {{ ref('stg_departments') }} d
    left join {{ ref('stg_courses') }} c on d.department_id = c.department_id
    left join {{ ref('int_course_performance_metrics') }} cpm on c.course_id = cpm.course_id
    group by d.department_name
),

competitive_analysis as (
    select
        ppm.program_name,
        ppm.department_code,
        ppm.total_students,
        ppm.faculty_count,
        ppm.course_offerings,
        ppm.program_avg_gpa,
        ppm.graduation_rate,
        ppm.honors_percentage,
        ppm.dropout_rate,
        fpm.revenue_per_student,
        fpm.cost_per_student,
        fpm.revenue_efficiency_ratio,
        fpm.faculty_cost_ratio,
        fqm.avg_faculty_experience,
        fqm.senior_faculty_percentage,
        fqm.avg_faculty_compensation,
        fqm.student_faculty_ratio,
        cqm.avg_course_rigor,
        cqm.advanced_course_percentage,
        cqm.avg_course_success_rate,
        cqm.avg_course_gpa,
        
        -- Competitive positioning scores (0-100 each)
        round(
            (case when ppm.graduation_rate >= 90 then 25
                  when ppm.graduation_rate >= 80 then 20
                  when ppm.graduation_rate >= 70 then 15
                  else 10 end) +
            (case when ppm.honors_percentage >= 15 then 25
                  when ppm.honors_percentage >= 10 then 20
                  when ppm.honors_percentage >= 5 then 15
                  else 10 end) +
            (case when ppm.program_avg_gpa >= 3.5 then 25
                  when ppm.program_avg_gpa >= 3.0 then 20
                  when ppm.program_avg_gpa >= 2.5 then 15
                  else 10 end) +
            (case when ppm.dropout_rate <= 5 then 25
                  when ppm.dropout_rate <= 10 then 20
                  when ppm.dropout_rate <= 15 then 15
                  else 10 end), 0
        ) as academic_excellence_score,
        
        round(
            (case when fpm.revenue_efficiency_ratio >= 1.5 then 30
                  when fpm.revenue_efficiency_ratio >= 1.2 then 25
                  when fpm.revenue_efficiency_ratio >= 1.0 then 20
                  else 10 end) +
            (case when fpm.cost_per_student <= 5000 then 35
                  when fpm.cost_per_student <= 8000 then 25
                  when fpm.cost_per_student <= 12000 then 15
                  else 5 end) +
            (case when fpm.faculty_cost_ratio <= 60 then 35
                  when fpm.faculty_cost_ratio <= 75 then 25
                  when fpm.faculty_cost_ratio <= 85 then 15
                  else 5 end), 0
        ) as financial_efficiency_score,
        
        round(
            (case when fqm.senior_faculty_percentage >= 40 then 30
                  when fqm.senior_faculty_percentage >= 30 then 25
                  when fqm.senior_faculty_percentage >= 20 then 20
                  else 15 end) +
            (case when fqm.avg_faculty_experience >= 15 then 25
                  when fqm.avg_faculty_experience >= 10 then 20
                  when fqm.avg_faculty_experience >= 7 then 15
                  else 10 end) +
            (case when fqm.student_faculty_ratio between 15 and 25 then 25
                  when fqm.student_faculty_ratio between 10 and 30 then 20
                  when fqm.student_faculty_ratio between 8 and 35 then 15
                  else 10 end) +
            (case when cqm.advanced_course_percentage >= 30 then 20
                  when cqm.advanced_course_percentage >= 20 then 15
                  when cqm.advanced_course_percentage >= 10 then 10
                  else 5 end), 0
        ) as program_quality_score
    from program_performance_metrics ppm
    left join financial_performance_metrics fpm on ppm.program_name = fpm.department_name
    left join faculty_quality_metrics fqm on ppm.program_name = fqm.department_name
    left join course_quality_metrics cqm on ppm.program_name = cqm.department_name
),

benchmarking_analysis as (
    select
        ca.*,
        (academic_excellence_score + financial_efficiency_score + program_quality_score) / 3 as overall_competitiveness_score,
        
        -- Rankings within institution
        row_number() over (order by academic_excellence_score desc) as academic_excellence_rank,
        row_number() over (order by financial_efficiency_score desc) as financial_efficiency_rank,
        row_number() over (order by program_quality_score desc) as program_quality_rank,
        row_number() over (order by (academic_excellence_score + financial_efficiency_score + program_quality_score) desc) as overall_competitiveness_rank,
        
        -- Percentile rankings
        percent_rank() over (order by graduation_rate) as graduation_rate_percentile,
        percent_rank() over (order by revenue_efficiency_ratio) as revenue_efficiency_percentile,
        percent_rank() over (order by program_avg_gpa) as gpa_percentile,
        percent_rank() over (order by senior_faculty_percentage) as faculty_quality_percentile,
        
        -- Institutional averages for comparison
        avg(graduation_rate) over () as institutional_avg_graduation_rate,
        avg(program_avg_gpa) over () as institutional_avg_gpa,
        avg(revenue_efficiency_ratio) over () as institutional_avg_revenue_efficiency,
        avg(senior_faculty_percentage) over () as institutional_avg_senior_faculty
    from competitive_analysis ca
),

strategic_positioning as (
    select
        ba.*,
        case
            when overall_competitiveness_score >= 80 then 'Market Leader'
            when overall_competitiveness_score >= 65 then 'Strong Competitor'
            when overall_competitiveness_score >= 50 then 'Average Performer'
            when overall_competitiveness_score >= 35 then 'Below Average'
            else 'Needs Significant Improvement'
        end as competitive_position,
        
        case
            when academic_excellence_score > program_quality_score and academic_excellence_score > financial_efficiency_score then 'Academic Excellence Focus'
            when financial_efficiency_score > program_quality_score then 'Cost Leadership Focus'
            when program_quality_score > financial_efficiency_score then 'Quality Differentiation Focus'
            else 'Balanced Approach'
        end as strategic_strength,
        
        case
            when academic_excellence_score < 40 then 'Improve academic outcomes and retention'
            when financial_efficiency_score < 40 then 'Optimize costs and improve revenue generation'
            when program_quality_score < 40 then 'Enhance faculty quality and curriculum rigor'
            when overall_competitiveness_rank > count(*) over () * 0.75 then 'Focus on core competency development'
            else 'Maintain competitive advantage and explore growth'
        end as strategic_recommendation,
        
        case
            when graduation_rate > institutional_avg_graduation_rate * 1.2 and 
                 program_avg_gpa > institutional_avg_gpa * 1.1 then 'Flagship Program'
            when revenue_efficiency_ratio > institutional_avg_revenue_efficiency * 1.3 then 'High Value Program'
            when senior_faculty_percentage > institutional_avg_senior_faculty * 1.5 then 'Premium Quality Program'
            when graduation_rate < institutional_avg_graduation_rate * 0.8 then 'At-Risk Program'
            else 'Standard Program'
        end as program_classification,
        
        -- Investment priority (simplified to avoid column reference issues)
        'Standard Investment' as investment_priority
    from benchmarking_analysis ba
)

select * from strategic_positioning
order by overall_competitiveness_score desc