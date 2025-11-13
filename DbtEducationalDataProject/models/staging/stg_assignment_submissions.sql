{{ config(materialized='view') }}

with source_data as (
    select
        submission_id,
        assignment_id,
        student_id,
        submission_date,
        score,
        late_submission,
        feedback,
        case
            when score is null then 'Not Graded'
            when score = 0 then 'Zero Score'
            when score > 0 then 'Graded'
            else 'Unknown'
        end as grading_status,
        case
            when late_submission then 'Late'
            else 'On Time'
        end as submission_timeliness,
        case
            when feedback is not null and trim(feedback) != '' then 'Has Feedback'
            else 'No Feedback'
        end as feedback_status,
        created_at
    from {{ source('raw_edu', 'assignment_submissions') }}
)

select * from source_data