{{ config(materialized='table') }}

with tuition_data as (
    select
        tp.payment_id,
        tp.student_id,
        tp.semester_id,
        tp.amount,
        tp.payment_date,
        tp.payment_method_category,
        tp.late_fee,
        tp.total_payment,
        tp.payment_timeliness,
        tp.payment_year,
        tp.payment_month,
        sem.semester_name,
        sem.academic_year,
        sem.semester_type,
        sem.start_date as semester_start,
        sem.end_date as semester_end,
        s.student_status,
        s.gpa,
        s.academic_standing,
        s.major_id,
        d.department_name,
        d.department_code,
        d.budget as department_budget,
        extract(quarter from tp.payment_date) as payment_quarter
    from {{ ref('stg_tuition_payments') }} tp
    left join {{ ref('stg_semesters') }} sem on tp.semester_id = sem.semester_id
    left join {{ ref('stg_students') }} s on tp.student_id = s.student_id
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
),

revenue_metrics as (
    select
        semester_id,
        semester_name,
        academic_year,
        semester_type,
        semester_start,
        semester_end,
        department_name,
        department_code,
        payment_year,
        payment_quarter,
        count(distinct payment_id) as total_payments,
        count(distinct student_id) as paying_students,
        sum(amount) as total_tuition_revenue,
        sum(late_fee) as total_late_fees,
        sum(total_payment) as total_revenue_with_fees,
        avg(amount) as avg_tuition_payment,
        min(amount) as min_payment,
        max(amount) as max_payment,
        count(case when payment_timeliness = 'Late Payment' then 1 end) as late_payments,
        count(case when payment_method_category = 'Credit Card' then 1 end) as credit_card_payments,
        count(case when payment_method_category = 'Bank Transfer' then 1 end) as bank_transfer_payments,
        count(case when payment_method_category = 'Check' then 1 end) as check_payments,
        round(
            count(case when payment_timeliness = 'Late Payment' then 1 end) * 100.0 / 
            nullif(count(payment_id), 0), 2
        ) as late_payment_percentage,
        round(
            sum(late_fee) * 100.0 / nullif(sum(total_payment), 0), 2
        ) as late_fee_percentage_of_revenue
    from tuition_data
    group by 
        semester_id, semester_name, academic_year, semester_type, semester_start, 
        semester_end, department_name, department_code, payment_year, payment_quarter
),

comparative_analysis as (
    select
        *,
        lag(total_tuition_revenue) over (
            partition by department_name 
            order by payment_year, payment_quarter
        ) as prev_period_revenue,
        round(
            (total_tuition_revenue - lag(total_tuition_revenue) over (
                partition by department_name 
                order by payment_year, payment_quarter
            )) * 100.0 / nullif(lag(total_tuition_revenue) over (
                partition by department_name 
                order by payment_year, payment_quarter
            ), 0), 2
        ) as revenue_growth_rate,
        case
            when total_tuition_revenue >= 100000 then 'High Revenue'
            when total_tuition_revenue >= 50000 then 'Moderate Revenue'
            when total_tuition_revenue >= 25000 then 'Low Revenue'
            else 'Minimal Revenue'
        end as revenue_category,
        case
            when late_payment_percentage >= 20 then 'High Collection Risk'
            when late_payment_percentage >= 10 then 'Moderate Collection Risk'
            when late_payment_percentage >= 5 then 'Low Collection Risk'
            else 'Minimal Collection Risk'
        end as collection_risk_category,
        round(total_tuition_revenue / nullif(paying_students, 0), 2) as revenue_per_student,
        round(total_late_fees / nullif(late_payments, 0), 2) as avg_late_fee_per_late_payment
    from revenue_metrics
)

select * from comparative_analysis