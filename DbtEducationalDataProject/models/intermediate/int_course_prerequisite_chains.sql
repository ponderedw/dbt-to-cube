{{ config(materialized='view') }}

with recursive course_hierarchy as (
    -- Base case: courses with no prerequisites
    select
        course_id,
        course_code,
        course_name,
        prerequisite_course_id,
        department_id,
        difficulty_level,
        credits,
        0 as prerequisite_depth,
        course_code as prerequisite_chain,
        cast(null as int) as root_course_id
    from {{ ref('stg_courses') }}
    where prerequisite_course_id is null

    union all

    -- Recursive case: courses with prerequisites
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.prerequisite_course_id,
        c.department_id,
        c.difficulty_level,
        c.credits,
        ch.prerequisite_depth + 1,
        ch.prerequisite_chain || ' -> ' || c.course_code as prerequisite_chain,
        coalesce(ch.root_course_id, ch.course_id) as root_course_id
    from {{ ref('stg_courses') }} c
    join course_hierarchy ch on c.prerequisite_course_id = ch.course_id
    where ch.prerequisite_depth < 10  -- Prevent infinite recursion
),

prerequisite_analysis as (
    select
        ch.*,
        d.department_name,
        d.department_code,
        prereq.course_code as prerequisite_code,
        prereq.course_name as prerequisite_name,
        prereq.difficulty_level as prerequisite_difficulty,
        case
            when ch.prerequisite_depth = 0 then 'Entry Level'
            when ch.prerequisite_depth = 1 then 'Second Level'
            when ch.prerequisite_depth = 2 then 'Intermediate'
            when ch.prerequisite_depth = 3 then 'Advanced'
            when ch.prerequisite_depth >= 4 then 'Expert Level'
        end as course_level_category,
        case
            when ch.prerequisite_depth = 0 then 'No Prerequisites'
            when ch.prerequisite_depth = 1 then 'Single Prerequisite'
            when ch.prerequisite_depth between 2 and 3 then 'Multiple Prerequisites'
            else 'Complex Prerequisite Chain'
        end as prerequisite_complexity,
        ch.difficulty_level - coalesce(prereq.difficulty_level, 0) as difficulty_progression
    from course_hierarchy ch
    left join {{ ref('stg_departments') }} d on ch.department_id = d.department_id
    left join {{ ref('stg_courses') }} prereq on ch.prerequisite_course_id = prereq.course_id
),

course_sequence_metrics as (
    select
        root_course_id,
        count(*) as total_courses_in_sequence,
        max(prerequisite_depth) as max_sequence_depth,
        min(difficulty_level) as min_difficulty_in_sequence,
        max(difficulty_level) as max_difficulty_in_sequence,
        avg(difficulty_level) as avg_difficulty_in_sequence,
        sum(credits) as total_credits_in_sequence,
        string_agg(course_code, ' -> ' order by prerequisite_depth) as full_sequence
    from prerequisite_analysis
    where root_course_id is not null
    group by root_course_id
),

final_analysis as (
    select
        pa.*,
        csm.total_courses_in_sequence,
        csm.max_sequence_depth,
        csm.min_difficulty_in_sequence,
        csm.max_difficulty_in_sequence,
        csm.avg_difficulty_in_sequence,
        csm.total_credits_in_sequence,
        csm.full_sequence,
        case
            when csm.max_sequence_depth >= 4 then 'Long Sequence'
            when csm.max_sequence_depth >= 2 then 'Moderate Sequence'
            when csm.max_sequence_depth = 1 then 'Short Sequence'
            else 'No Sequence'
        end as sequence_length_category,
        case
            when pa.difficulty_progression > 2 then 'Steep Difficulty Increase'
            when pa.difficulty_progression > 0 then 'Moderate Difficulty Increase'
            when pa.difficulty_progression = 0 then 'Same Difficulty Level'
            else 'Difficulty Decrease'
        end as difficulty_progression_category
    from prerequisite_analysis pa
    left join course_sequence_metrics csm on pa.root_course_id = csm.root_course_id
)

select * from final_analysis