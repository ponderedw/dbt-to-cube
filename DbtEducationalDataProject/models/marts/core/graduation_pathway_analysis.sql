{{ config(materialized='table') }}

with student_degree_progress as (
    select
        s.student_id,
        s.full_name,
        s.enrollment_date,
        s.graduation_date,
        s.student_status,
        s.gpa,
        s.years_enrolled,
        d.department_name as major,
        d.department_code,
        eh.total_credits_earned,
        eh.total_credits_attempted,
        eh.failed_courses_count,
        eh.withdrawn_courses_count,
        case
            when s.graduation_date is not null then 
                extract(year from s.graduation_date) - extract(year from s.enrollment_date)
            else 
                extract(year from current_date) - extract(year from s.enrollment_date)
        end as actual_years_to_degree,
        case when s.graduation_date is not null then 1 else 0 end as has_graduated,
        120 as required_credits_for_graduation,  -- Standard bachelor's degree
        120 - eh.total_credits_earned as credits_remaining
    from {{ ref('stg_students') }} s
    left join {{ ref('stg_departments') }} d on s.major_id = d.department_id
    left join (
        select 
            student_id,
            max(total_credits_earned) as total_credits_earned,
            max(total_credits_attempted) as total_credits_attempted,
            max(failed_courses_count) as failed_courses_count,
            max(withdrawn_courses_count) as withdrawn_courses_count
        from {{ ref('int_student_enrollment_history') }}
        group by student_id
    ) eh on s.student_id = eh.student_id
),

course_sequencing as (
    select
        eh.student_id,
        c.department_id,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        c.prerequisite_course_id,
        prereq.course_code as prerequisite_code,
        eh.semester_id,
        sem.semester_name,
        sem.start_date,
        row_number() over (partition by eh.student_id order by sem.start_date) as course_sequence_number,
        case when c.prerequisite_course_id is not null then 1 else 0 end as has_prerequisite,
        eh.grade_points,
        eh.grade_category
    from {{ ref('int_student_enrollment_history') }} eh
    inner join {{ ref('stg_courses') }} c on eh.course_id = c.course_id
    left join {{ ref('stg_courses') }} prereq on c.prerequisite_course_id = prereq.course_id
    inner join {{ ref('stg_semesters') }} sem on eh.semester_id = sem.semester_id
),

pathway_efficiency as (
    select
        sdp.student_id,
        sdp.full_name,
        sdp.major,
        sdp.department_code,
        sdp.enrollment_date,
        sdp.graduation_date,
        sdp.student_status,
        sdp.gpa,
        sdp.years_enrolled,
        sdp.actual_years_to_degree,
        sdp.total_credits_earned,
        sdp.total_credits_attempted,
        sdp.credits_remaining,
        sdp.has_graduated,
        sdp.failed_courses_count,
        sdp.withdrawn_courses_count,
        round(sdp.total_credits_earned::numeric / sdp.total_credits_attempted * 100, 2) as credit_efficiency,
        case
            when sdp.has_graduated = 1 and sdp.actual_years_to_degree <= 4 then 'On-Time Graduate'
            when sdp.has_graduated = 1 and sdp.actual_years_to_degree between 4 and 5 then 'Extended Graduate'
            when sdp.has_graduated = 1 and sdp.actual_years_to_degree > 5 then 'Significantly Delayed Graduate'
            when sdp.student_status = 'active' and sdp.years_enrolled <= 4 then 'On Track'
            when sdp.student_status = 'active' and sdp.years_enrolled between 4 and 6 then 'Extended Timeline'
            when sdp.student_status = 'active' and sdp.years_enrolled > 6 then 'Significantly Delayed'
            else 'Did Not Complete'
        end as degree_completion_status,
        case
            when sdp.total_credits_earned >= 120 then 'Graduation Eligible'
            when sdp.total_credits_earned >= 90 then 'Senior Status'
            when sdp.total_credits_earned >= 60 then 'Junior Status'
            when sdp.total_credits_earned >= 30 then 'Sophomore Status'
            else 'Freshman Status'
        end as academic_classification,
        round(sdp.total_credits_earned::numeric / greatest(sdp.years_enrolled, 1), 2) as avg_credits_per_year,
        cs.avg_course_difficulty,
        cs.prerequisite_courses_taken,
        cs.advanced_courses_taken
    from student_degree_progress sdp
    left join (
        select
            student_id,
            avg(difficulty_level) as avg_course_difficulty,
            count(case when has_prerequisite = 1 then 1 end) as prerequisite_courses_taken,
            count(case when difficulty_level >= 4 then 1 end) as advanced_courses_taken,
            max(course_sequence_number) as total_courses_in_sequence
        from course_sequencing
        group by student_id
    ) cs on sdp.student_id = cs.student_id
),

degree_pathway_patterns as (
    select
        major,
        department_code,
        count(*) as total_students_in_major,
        count(case when has_graduated = 1 then 1 end) as graduates_count,
        count(case when student_status = 'active' then 1 end) as active_students_count,
        round(
            count(case when has_graduated = 1 then 1 end) * 100.0 / 
            nullif(count(case when student_status in ('active', 'graduated', 'dropped') then 1 end), 0), 2
        ) as graduation_rate,
        avg(case when has_graduated = 1 then actual_years_to_degree end) as avg_years_to_graduate,
        avg(case when has_graduated = 1 then total_credits_attempted end) as avg_credits_attempted,
        avg(case when has_graduated = 1 then credit_efficiency end) as avg_graduation_efficiency,
        count(case when degree_completion_status = 'On-Time Graduate' then 1 end) as on_time_graduates,
        count(case when degree_completion_status like '%Delayed%' then 1 end) as delayed_graduates,
        round(
            count(case when degree_completion_status = 'On-Time Graduate' then 1 end) * 100.0 / 
            nullif(count(case when has_graduated = 1 then 1 end), 0), 2
        ) as on_time_graduation_rate
    from pathway_efficiency
    group by major, department_code
),

final_pathway_analysis as (
    select
        pe.*,
        dpp.graduation_rate as major_graduation_rate,
        dpp.avg_years_to_graduate as major_avg_years,
        dpp.avg_graduation_efficiency as major_avg_efficiency,
        dpp.on_time_graduation_rate as major_on_time_rate,
        case
            when pe.credit_efficiency >= 95 then 'Highly Efficient'
            when pe.credit_efficiency >= 85 then 'Efficient'
            when pe.credit_efficiency >= 75 then 'Moderately Efficient'
            else 'Inefficient'
        end as individual_efficiency_category,
        case
            when pe.avg_credits_per_year >= 15 then 'Fast Track'
            when pe.avg_credits_per_year >= 12 then 'Standard Pace'
            when pe.avg_credits_per_year >= 9 then 'Slow Pace'
            else 'Very Slow Pace'
        end as progression_pace,
        case
            when pe.has_graduated = 0 and pe.credits_remaining <= 30 and pe.gpa >= 2.0 then 'Expected to Graduate Soon'
            when pe.has_graduated = 0 and pe.credits_remaining <= 60 and pe.gpa >= 2.0 then 'On Track to Graduate'
            when pe.has_graduated = 0 and pe.gpa < 2.0 then 'At Risk'
            when pe.has_graduated = 0 and pe.years_enrolled > 6 then 'Extended Timeline Risk'
            else 'Standard Progress'
        end as completion_risk_assessment
    from pathway_efficiency pe
    left join degree_pathway_patterns dpp on pe.major = dpp.major
)

select * from final_pathway_analysis
order by student_id