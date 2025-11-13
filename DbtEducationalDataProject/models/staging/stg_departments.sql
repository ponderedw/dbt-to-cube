{{ config(materialized='view') }}

with source_data as (
    select
        department_id,
        department_name,
        department_code,
        head_faculty_id,
        budget,
        building_location,
        case 
            when budget >= 3000000 then 'Large'
            when budget >= 2000000 then 'Medium'
            when budget >= 1000000 then 'Small'
            else 'Micro'
        end as department_size,
        round(budget / 1000000.0, 2) as budget_millions,
        created_at
    from {{ source('raw_edu', 'departments') }}
)

select * from source_data