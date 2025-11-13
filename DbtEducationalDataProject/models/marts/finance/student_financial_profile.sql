{{ config(materialized='table') }}

with student_finances as (
    select
        s.student_id,
        s.full_name,
        s.email,
        s.student_status,
        s.gpa,
        s.academic_standing,
        s.years_enrolled,
        d.department_name as major_department,
        fa.aid_id,
        fa.aid_type,
        fa.aid_category,
        fa.amount as aid_amount,
        fa.academic_year as aid_academic_year,
        fa.support_level,
        fa.disbursement_period,
        tp.payment_id,
        tp.semester_id,
        tp.amount as payment_amount,
        tp.payment_date,
        tp.payment_method_category,
        tp.late_fee,
        tp.total_payment,
        tp.payment_timeliness,
        tp.payment_size_category,
        sem.semester_name,
        sem.academic_year as payment_academic_year
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join {{ ref('stg_financial_aid') }} fa on s.student_id = fa.student_id
    left join {{ ref('stg_tuition_payments') }} tp on s.student_id = tp.student_id
    left join {{ ref('stg_semesters') }} sem on tp.semester_id = sem.semester_id
),

financial_summary as (
    select
        student_id,
        full_name,
        email,
        student_status,
        gpa,
        academic_standing,
        years_enrolled,
        major_department,
        count(distinct aid_id) as total_aid_awards,
        sum(aid_amount) as total_aid_received,
        avg(aid_amount) as avg_aid_amount,
        count(distinct payment_id) as total_payments_made,
        sum(payment_amount) as total_tuition_paid,
        sum(late_fee) as total_late_fees,
        sum(total_payment) as total_amount_paid,
        avg(payment_amount) as avg_payment_amount,
        count(case when payment_timeliness = 'Late Payment' then 1 end) as late_payments_count,
        round(
            count(case when payment_timeliness = 'Late Payment' then 1 end) * 100.0 / 
            nullif(count(payment_id), 0), 2
        ) as late_payment_rate,
        max(case when aid_category = 'Merit-Based' then aid_amount else 0 end) as max_merit_aid,
        max(case when aid_category = 'Need-Based' then aid_amount else 0 end) as max_need_aid,
        max(case when aid_category = 'Loan' then aid_amount else 0 end) as max_loan_amount,
        count(distinct aid_academic_year) as aid_years_count,
        count(distinct payment_academic_year) as payment_years_count
    from student_finances
    where student_id is not null
    group by 
        student_id, full_name, email, student_status, gpa, 
        academic_standing, years_enrolled, major_department
),

financial_analysis as (
    select
        *,
        case
            when total_aid_received >= 20000 then 'High Aid Recipient'
            when total_aid_received >= 10000 then 'Moderate Aid Recipient'
            when total_aid_received >= 5000 then 'Low Aid Recipient'
            when total_aid_received > 0 then 'Minimal Aid Recipient'
            else 'No Aid Received'
        end as aid_recipient_category,
        case
            when late_payment_rate = 0 then 'Excellent Payment History'
            when late_payment_rate <= 10 then 'Good Payment History'
            when late_payment_rate <= 25 then 'Fair Payment History'
            else 'Poor Payment History'
        end as payment_reliability,
        case
            when total_late_fees = 0 then 'No Late Fees'
            when total_late_fees <= 100 then 'Minimal Late Fees'
            when total_late_fees <= 500 then 'Moderate Late Fees'
            else 'High Late Fees'
        end as late_fee_category,
        round(total_aid_received / nullif(years_enrolled, 0), 2) as avg_aid_per_year,
        round(total_tuition_paid / nullif(years_enrolled, 0), 2) as avg_tuition_per_year,
        case
            when max_merit_aid > max_need_aid and max_merit_aid > max_loan_amount then 'Merit-Based Primary'
            when max_need_aid > max_loan_amount then 'Need-Based Primary'
            when max_loan_amount > 0 then 'Loan-Based Primary'
            else 'No Primary Aid Type'
        end as primary_aid_type
    from financial_summary
)

select * from financial_analysis