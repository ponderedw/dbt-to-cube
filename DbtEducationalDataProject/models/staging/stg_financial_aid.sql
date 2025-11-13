{{ config(materialized='view') }}

with source_data as (
    select
        aid_id,
        student_id,
        aid_type,
        amount,
        academic_year,
        disbursement_date,
        case
            when aid_type ilike '%scholarship%' then 'Merit-Based'
            when aid_type ilike '%grant%' then 'Need-Based'
            when aid_type ilike '%loan%' then 'Loan'
            when aid_type ilike '%work%' then 'Work-Study'
            else 'Other'
        end as aid_category,
        case
            when amount >= 10000 then 'High Support'
            when amount >= 5000 then 'Medium Support'
            when amount >= 1000 then 'Low Support'
            else 'Minimal Support'
        end as support_level,
        extract(year from disbursement_date) as disbursement_year,
        extract(month from disbursement_date) as disbursement_month,
        case
            when extract(month from disbursement_date) between 8 and 12 then 'Fall Disbursement'
            when extract(month from disbursement_date) between 1 and 5 then 'Spring Disbursement'
            else 'Summer Disbursement'
        end as disbursement_period,
        created_at
    from {{ source('raw_edu', 'financial_aid') }}
)

select * from source_data