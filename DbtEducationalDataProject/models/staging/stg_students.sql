{{ config(materialized='view') }}

with source_data as (
    select
        student_id,
        first_name,
        last_name,
        first_name || ' ' || last_name as full_name,
        email,
        date_of_birth,
        enrollment_date,
        graduation_date,
        student_status,
        gpa,
        major_id,
        advisor_id,
        address_id,
        extract(year from age(current_date, date_of_birth)) as age,
        extract(year from age(current_date, enrollment_date)) as years_enrolled,
        case 
            when gpa >= 3.5 then 'Dean''s List'
            when gpa >= 3.0 then 'Good Standing'
            when gpa >= 2.0 then 'Academic Warning'
            else 'Academic Probation'
        end as academic_standing,
        case
            when graduation_date is not null then 'Graduated'
            when student_status = 'active' and gpa >= 2.0 then 'Active'
            when student_status = 'active' and gpa < 2.0 then 'At Risk'
            else initcap(student_status)
        end as current_status,
        created_at
    from {{ source('raw_edu', 'students') }}
)

select * from source_data