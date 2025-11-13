{{ config(materialized='view') }}

with course_sequence_data as (
    select
        e.student_id,
        e.course_id,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        c.prerequisite_course_id,
        prereq.course_code as prerequisite_code,
        e.semester_id,
        sem.start_date,
        e.grade_points,
        e.grade_category,
        row_number() over (partition by e.student_id order by sem.start_date) as sequence_order
    from {{ ref('stg_enrollments') }} e
    inner join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    left join {{ ref('stg_courses') }} prereq on c.prerequisite_course_id = prereq.course_id
    inner join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    where e.enrollment_status = 'Completed'
),

prerequisite_compliance as (
    select
        csd.student_id,
        csd.course_id,
        csd.course_code,
        csd.prerequisite_course_id,
        csd.prerequisite_code,
        csd.sequence_order,
        case 
            when csd.prerequisite_course_id is null then 'No Prerequisite Required'
            when prereq_taken.course_id is not null then 'Prerequisite Completed'
            else 'Prerequisite Not Completed'
        end as prerequisite_status,
        case
            when csd.prerequisite_course_id is not null and prereq_taken.course_id is not null then
                csd.sequence_order - prereq_taken.sequence_order
            else null
        end as courses_between_prerequisite
    from course_sequence_data csd
    left join course_sequence_data prereq_taken
        on csd.student_id = prereq_taken.student_id
        and csd.prerequisite_course_id = prereq_taken.course_id
        and prereq_taken.sequence_order < csd.sequence_order
),

curriculum_pathways as (
    select
        student_id,
        string_agg(pc.course_code, ' -> ' order by pc.sequence_order) as learning_pathway,
        count(*) as total_courses_taken,
        count(case when prerequisite_status = 'Prerequisite Not Completed' then 1 end) as prerequisite_violations,
        avg(case when pc.prerequisite_course_id is not null then courses_between_prerequisite end) as avg_gap_from_prerequisite,
        count(case when difficulty_level = 1 then 1 end) as beginner_courses,
        count(case when difficulty_level = 2 then 1 end) as intermediate_courses,
        count(case when difficulty_level >= 3 then 1 end) as advanced_courses
    from prerequisite_compliance pc
    inner join course_sequence_data csd using (student_id, course_id)
    group by student_id
),

difficulty_progression_analysis as (
    select
        student_id,
        difficulty_level,
        sequence_order,
        lag(difficulty_level) over (partition by student_id order by sequence_order) as prev_difficulty,
        difficulty_level - lag(difficulty_level) over (partition by student_id order by sequence_order) as difficulty_jump,
        grade_points,
        lag(grade_points) over (partition by student_id order by sequence_order) as prev_grade_points,
        grade_points - lag(grade_points) over (partition by student_id order by sequence_order) as grade_change
    from course_sequence_data
),

progression_patterns as (
    select
        student_id,
        count(case when difficulty_jump > 2 then 1 end) as large_difficulty_jumps,
        count(case when difficulty_jump < 0 then 1 end) as difficulty_reversions,
        avg(case when difficulty_jump > 0 then grade_change end) as avg_grade_change_on_difficulty_increase,
        count(case when difficulty_jump > 0 and grade_change < -0.5 then 1 end) as struggled_with_difficulty_increase,
        max(difficulty_level) as highest_difficulty_attempted,
        count(case when prev_difficulty is not null then 1 end) as total_transitions
    from difficulty_progression_analysis
    where prev_difficulty is not null
    group by student_id
),

curriculum_effectiveness as (
    select
        cp.student_id,
        cp.learning_pathway,
        cp.total_courses_taken,
        cp.prerequisite_violations,
        cp.avg_gap_from_prerequisite,
        cp.beginner_courses,
        cp.intermediate_courses,
        cp.advanced_courses,
        pp.large_difficulty_jumps,
        pp.difficulty_reversions,
        pp.avg_grade_change_on_difficulty_increase,
        pp.struggled_with_difficulty_increase,
        pp.highest_difficulty_attempted,
        s.gpa as final_gpa,
        s.academic_standing,
        s.student_status,
        case
            when cp.prerequisite_violations = 0 then 'Perfect Compliance'
            when cp.prerequisite_violations <= 2 then 'Minor Violations'
            when cp.prerequisite_violations <= 5 then 'Moderate Violations'
            else 'Major Violations'
        end as prerequisite_compliance_category,
        case
            when pp.large_difficulty_jumps = 0 and pp.difficulty_reversions = 0 then 'Smooth Progression'
            when pp.large_difficulty_jumps <= 2 then 'Minor Progression Issues'
            when pp.large_difficulty_jumps <= 5 then 'Moderate Progression Issues'
            else 'Major Progression Issues'
        end as difficulty_progression_category,
        case
            when cp.beginner_courses > cp.advanced_courses * 2 then 'Beginner Heavy'
            when cp.advanced_courses > cp.beginner_courses then 'Advanced Heavy'
            else 'Balanced Curriculum'
        end as curriculum_balance,
        round(
            (case when prerequisite_violations = 0 then 30
                  when prerequisite_violations <= 2 then 25
                  when prerequisite_violations <= 5 then 15
                  else 5 end) +
            (case when large_difficulty_jumps = 0 then 25
                  when large_difficulty_jumps <= 2 then 20
                  when large_difficulty_jumps <= 4 then 15
                  else 10 end) +
            (case when avg_grade_change_on_difficulty_increase >= 0 then 25
                  when avg_grade_change_on_difficulty_increase >= -0.3 then 20
                  when avg_grade_change_on_difficulty_increase >= -0.7 then 15
                  else 10 end) +
            (case when highest_difficulty_attempted >= 4 then 20
                  when highest_difficulty_attempted >= 3 then 15
                  when highest_difficulty_attempted >= 2 then 10
                  else 5 end), 0
        ) as curriculum_pathway_score
    from curriculum_pathways cp
    left join progression_patterns pp on cp.student_id = pp.student_id
    left join {{ ref('stg_students') }} s on cp.student_id = s.student_id
),

pathway_recommendations as (
    select
        ce.*,
        case
            when prerequisite_violations > 3 then 'Implement stricter prerequisite enforcement'
            when large_difficulty_jumps > 3 then 'Add intermediate difficulty courses'
            when struggled_with_difficulty_increase > total_courses_taken * 0.3 then 'Provide additional academic support'
            when curriculum_balance = 'Beginner Heavy' then 'Encourage more challenging coursework'
            when difficulty_reversions > 2 then 'Review course sequencing recommendations'
            else 'Pathway appears appropriate'
        end as pathway_improvement_recommendation,
        case
            when curriculum_pathway_score >= 80 then 'Optimal Pathway'
            when curriculum_pathway_score >= 65 then 'Good Pathway'
            when curriculum_pathway_score >= 50 then 'Adequate Pathway'
            else 'Problematic Pathway'
        end as pathway_quality_assessment,
        case
            when prerequisite_compliance_category = 'Perfect Compliance' and 
                 difficulty_progression_category = 'Smooth Progression' and
                 final_gpa >= 3.0 then 'Exemplary Academic Journey'
            when prerequisite_violations <= 2 and large_difficulty_jumps <= 2 and final_gpa >= 2.5 then 'Successful Academic Journey'
            when prerequisite_violations > 5 or large_difficulty_jumps > 5 or final_gpa < 2.0 then 'Challenging Academic Journey'
            else 'Standard Academic Journey'
        end as overall_journey_assessment
    from curriculum_effectiveness ce
)

select * from pathway_recommendations
order by curriculum_pathway_score desc