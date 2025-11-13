{{ config(materialized='view') }}

with source_data as (
    select
        payment_id,
        student_id,
        semester_id,
        amount,
        payment_date,
        payment_method,
        late_fee,
        amount + coalesce(late_fee, 0) as total_payment,
        case
            when late_fee > 0 then 'Late Payment'
            else 'On Time Payment'
        end as payment_timeliness,
        case
            when payment_method ilike '%credit%' or payment_method ilike '%card%' then 'Credit Card'
            when payment_method ilike '%check%' then 'Check'
            when payment_method ilike '%transfer%' or payment_method ilike '%ach%' then 'Bank Transfer'
            when payment_method ilike '%cash%' then 'Cash'
            else 'Other'
        end as payment_method_category,
        extract(year from payment_date) as payment_year,
        extract(month from payment_date) as payment_month,
        case
            when amount >= 10000 then 'High Amount'
            when amount >= 5000 then 'Medium Amount'
            when amount >= 1000 then 'Low Amount'
            else 'Minimal Amount'
        end as payment_size_category,
        created_at
    from {{ source('raw_edu', 'tuition_payments') }}
)

select * from source_data