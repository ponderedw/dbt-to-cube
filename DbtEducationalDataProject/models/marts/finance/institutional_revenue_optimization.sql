{{ config(materialized='table') }}

with revenue_streams as (
    select
        sem.semester_id,
        sem.semester_name,
        sem.academic_year,
        sem.semester_type,
        d.department_id,
        d.department_name,
        d.budget as department_budget,
        count(distinct tp.student_id) as paying_students,
        count(distinct e.enrollment_id) as total_enrollments,
        sum(tp.amount) as tuition_revenue,
        sum(tp.late_fee) as late_fee_revenue,
        sum(tp.total_payment) as total_payment_revenue,
        sum(fa.amount) as financial_aid_disbursed,
        sum(c.credits * 500) as potential_tuition_at_standard_rate,  -- $500 per credit hour
        avg(tp.amount) as avg_tuition_per_student,
        sum(f.salary) as faculty_salary_costs,
        count(distinct f.faculty_id) as faculty_count
    from {{ ref('stg_semesters') }} sem
    left join {{ ref('stg_enrollments') }} e on sem.semester_id = e.semester_id
    left join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('stg_tuition_payments') }} tp on sem.semester_id = tp.semester_id and e.student_id = tp.student_id
    left join {{ ref('stg_financial_aid') }} fa on e.student_id = fa.student_id
    left join {{ ref('stg_class_sessions') }} cs on c.course_id = cs.course_id and sem.semester_id = cs.semester_id
    left join {{ ref('stg_faculty') }} f on cs.faculty_id = f.faculty_id
    group by 
        sem.semester_id, sem.semester_name, sem.academic_year, sem.semester_type,
        d.department_id, d.department_name, d.budget
),

cost_analysis as (
    select
        rs.*,
        -- Revenue metrics
        tuition_revenue - financial_aid_disbursed as net_tuition_revenue,
        potential_tuition_at_standard_rate - tuition_revenue as tuition_revenue_gap,
        round(tuition_revenue / nullif(potential_tuition_at_standard_rate, 0) * 100, 2) as tuition_collection_rate,
        
        -- Cost metrics
        faculty_salary_costs + (department_budget * 0.3) as estimated_total_costs,  -- Assuming 30% of budget for operations
        round(faculty_salary_costs / nullif(total_enrollments, 0), 2) as cost_per_enrollment,
        round(tuition_revenue / nullif(faculty_salary_costs, 0), 2) as revenue_to_faculty_cost_ratio,
        
        -- Efficiency metrics
        round(total_enrollments::numeric / nullif(faculty_count, 0), 2) as student_faculty_ratio,
        round(tuition_revenue / nullif(paying_students, 0), 2) as revenue_per_paying_student,
        round(total_enrollments::numeric / nullif(paying_students, 0), 2) as enrollment_to_payment_ratio,
        
        -- Aid impact
        round(financial_aid_disbursed / nullif(tuition_revenue + financial_aid_disbursed, 0) * 100, 2) as aid_percentage_of_gross_tuition
    from revenue_streams rs
),

optimization_opportunities as (
    select
        ca.*,
        -- Profitability analysis
        tuition_revenue - (faculty_salary_costs + (department_budget * 0.3)) as estimated_profit_loss,
        case
            when tuition_revenue - (faculty_salary_costs + (department_budget * 0.3)) > 0 then 'Profitable'
            when tuition_revenue - (faculty_salary_costs + (department_budget * 0.3)) > -50000 then 'Break Even'
            when tuition_revenue - (faculty_salary_costs + (department_budget * 0.3)) > -100000 then 'Minor Loss'
            else 'Major Loss'
        end as profitability_status,
        
        -- Optimization categories
        case
            when tuition_collection_rate < 80 then 'High Collection Risk'
            when tuition_collection_rate < 90 then 'Moderate Collection Risk'
            else 'Good Collection'
        end as collection_risk_category,
        
        case
            when student_faculty_ratio > 25 then 'Potential Faculty Shortage'
            when student_faculty_ratio < 10 then 'Potential Over-Staffing'
            else 'Optimal Staffing'
        end as staffing_optimization,
        
        case
            when aid_percentage_of_gross_tuition > 40 then 'High Aid Dependency'
            when aid_percentage_of_gross_tuition > 25 then 'Moderate Aid Dependency'
            else 'Low Aid Dependency'
        end as aid_dependency_level,
        
        -- Revenue optimization opportunities
        case
            when tuition_revenue_gap > 100000 then 'High Revenue Opportunity'
            when tuition_revenue_gap > 50000 then 'Moderate Revenue Opportunity'
            when tuition_revenue_gap > 0 then 'Small Revenue Opportunity'
            else 'Revenue Maximized'
        end as revenue_opportunity_level,
        
        -- Cost optimization recommendations
        case
            when cost_per_enrollment > 2000 then 'Review Cost Structure'
            when revenue_to_faculty_cost_ratio < 1.5 then 'Faculty Cost Efficiency Concern'
            when student_faculty_ratio < 12 then 'Consider Course Consolidation'
            when enrollment_to_payment_ratio > 1.2 then 'Payment Collection Issues'
            else 'Cost Structure Acceptable'
        end as cost_optimization_recommendation
    from cost_analysis ca
),

strategic_insights as (
    select
        oo.*,
        -- Strategic recommendations
        case
            when profitability_status in ('Minor Loss', 'Major Loss') and revenue_opportunity_level like '%High%' then 
                'Focus on enrollment growth and tuition collection'
            when profitability_status in ('Minor Loss', 'Major Loss') and staffing_optimization = 'Potential Over-Staffing' then
                'Consider faculty optimization or course load increase'
            when collection_risk_category != 'Good Collection' then
                'Implement enhanced payment collection strategies'
            when aid_dependency_level = 'High Aid Dependency' then
                'Diversify revenue streams and review aid policies'
            when revenue_opportunity_level like '%High%' then
                'Expand program capacity and marketing'
            else 'Maintain current operations with minor optimizations'
        end as primary_strategic_recommendation,
        
        -- Financial health score (0-100)
        round(
            (case when profitability_status = 'Profitable' then 30
                  when profitability_status = 'Break Even' then 20
                  when profitability_status = 'Minor Loss' then 10
                  else 0 end) +
            (case when tuition_collection_rate >= 95 then 25
                  when tuition_collection_rate >= 85 then 20
                  when tuition_collection_rate >= 75 then 15
                  else 10 end) +
            (case when student_faculty_ratio between 15 and 25 then 25
                  when student_faculty_ratio between 10 and 30 then 20
                  when student_faculty_ratio between 8 and 35 then 15
                  else 10 end) +
            (case when aid_dependency_level = 'Low Aid Dependency' then 20
                  when aid_dependency_level = 'Moderate Aid Dependency' then 15
                  else 10 end), 0
        ) as financial_health_score,
        
        -- Risk level
        case
            when estimated_profit_loss < -100000 and tuition_collection_rate < 75 then 'High Risk'
            when estimated_profit_loss < -50000 or tuition_collection_rate < 80 then 'Moderate Risk'
            when estimated_profit_loss < 0 or tuition_collection_rate < 90 then 'Low Risk'
            else 'Low Risk'
        end as financial_risk_level
    from optimization_opportunities oo
)

select * from strategic_insights
order by financial_health_score desc, department_name