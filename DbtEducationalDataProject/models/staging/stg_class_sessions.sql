{{ config(materialized='view') }}

with source_data as (
    select
        session_id,
        course_id,
        faculty_id,
        semester_id,
        session_time,
        session_date,
        room_id,
        attendance_count,
        extract(dow from session_date) as day_of_week,
        extract(hour from session_time) as session_hour,
        case
            when extract(hour from session_time) between 8 and 11 then 'Morning'
            when extract(hour from session_time) between 12 and 16 then 'Afternoon'
            when extract(hour from session_time) between 17 and 21 then 'Evening'
            else 'Night'
        end as time_block,
        case
            when extract(dow from session_date) = 0 then 'Sunday'
            when extract(dow from session_date) = 1 then 'Monday'
            when extract(dow from session_date) = 2 then 'Tuesday'
            when extract(dow from session_date) = 3 then 'Wednesday'
            when extract(dow from session_date) = 4 then 'Thursday'
            when extract(dow from session_date) = 5 then 'Friday'
            when extract(dow from session_date) = 6 then 'Saturday'
        end as day_name,
        created_at
    from {{ source('raw_edu', 'class_sessions') }}
)

select * from source_data