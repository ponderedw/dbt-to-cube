{{ config(materialized='table') }}

with course_performance_data as (
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.difficulty_level as assigned_difficulty,
        c.credits,
        c.prerequisite_course_id,
        d.department_name,
        cpm.total_enrollments,
        cpm.avg_grade_points,
        cpm.pass_rate,
        cpm.withdrawal_rate,
        cpm.avg_attendance,
        prereq.difficulty_level as prerequisite_difficulty,
        ia.avg_percentage_score as avg_assignment_score,
        ia.late_submission_rate
    from {{ ref('stg_courses') }} c
    left join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('int_course_performance_metrics') }} cpm on c.course_id = cpm.course_id
    left join {{ ref('stg_courses') }} prereq on c.prerequisite_course_id = prereq.course_id
    left join (
        select 
            course_id,
            avg(avg_percentage_score) as avg_percentage_score,
            avg(late_submission_rate) as late_submission_rate
        from {{ ref('int_assignment_performance') }}
        group by course_id
    ) ia on c.course_id = ia.course_id
),

difficulty_analysis as (
    select
        *,
        -- Performance-based difficulty assessment
        case
            when avg_grade_points >= 3.5 and pass_rate >= 90 then 1
            when avg_grade_points >= 3.0 and pass_rate >= 80 then 2
            when avg_grade_points >= 2.5 and pass_rate >= 70 then 3
            when avg_grade_points >= 2.0 and pass_rate >= 60 then 4
            else 5
        end as performance_based_difficulty,
        
        -- Engagement-based difficulty assessment
        case
            when avg_attendance >= 95 and late_submission_rate <= 10 then 1
            when avg_attendance >= 85 and late_submission_rate <= 20 then 2
            when avg_attendance >= 75 and late_submission_rate <= 30 then 3
            when avg_attendance >= 65 and late_submission_rate <= 40 then 4
            else 5
        end as engagement_based_difficulty,
        
        -- Withdrawal-based difficulty assessment
        case
            when withdrawal_rate <= 5 then 1
            when withdrawal_rate <= 10 then 2
            when withdrawal_rate <= 15 then 3
            when withdrawal_rate <= 25 then 4
            else 5
        end as withdrawal_based_difficulty
    from course_performance_data
    where total_enrollments >= 3  -- Only courses with sufficient data
),

composite_difficulty as (
    select
        da.*,
        round(
            (performance_based_difficulty + engagement_based_difficulty + withdrawal_based_difficulty) / 3.0, 1
        ) as calculated_difficulty,
        abs(assigned_difficulty - round(
            (performance_based_difficulty + engagement_based_difficulty + withdrawal_based_difficulty) / 3.0, 1
        )) as difficulty_calibration_error,
        case
            when prerequisite_course_id is not null and prerequisite_difficulty is not null then
                assigned_difficulty - prerequisite_difficulty
            else null
        end as difficulty_progression_from_prerequisite
    from difficulty_analysis da
),

calibration_assessment as (
    select
        cd.*,
        case
            when difficulty_calibration_error <= 0.5 then 'Well Calibrated'
            when difficulty_calibration_error <= 1.0 then 'Moderately Calibrated'
            when difficulty_calibration_error <= 1.5 then 'Poorly Calibrated'
            else 'Very Poorly Calibrated'
        end as calibration_status,
        
        case
            when calculated_difficulty > assigned_difficulty + 1 then 'Course Harder Than Expected'
            when calculated_difficulty > assigned_difficulty + 0.5 then 'Course Somewhat Harder'
            when calculated_difficulty < assigned_difficulty - 1 then 'Course Easier Than Expected'
            when calculated_difficulty < assigned_difficulty - 0.5 then 'Course Somewhat Easier'
            else 'Course As Expected'
        end as difficulty_assessment,
        
        case
            when difficulty_progression_from_prerequisite is not null then
                case
                    when difficulty_progression_from_prerequisite < 0 then 'Easier than prerequisite'
                    when difficulty_progression_from_prerequisite = 0 then 'Same difficulty as prerequisite'
                    when difficulty_progression_from_prerequisite = 1 then 'Appropriate progression'
                    when difficulty_progression_from_prerequisite > 1 then 'Large difficulty jump'
                    else 'Unknown progression'
                end
            else 'No prerequisite for comparison'
        end as prerequisite_progression_assessment,
        
        -- Recommendations for difficulty recalibration
        case
            when calculated_difficulty > assigned_difficulty + 1 and pass_rate < 60 then
                'Consider reducing course difficulty or improving support'
            when calculated_difficulty < assigned_difficulty - 1 and pass_rate > 95 then
                'Consider increasing course rigor or advancing difficulty level'
            when withdrawal_rate > 20 then
                'High dropout rate suggests course may be too demanding'
            when avg_attendance < 70 then
                'Low engagement suggests course structure review needed'
            when difficulty_calibration_error > 1.5 then
                'Significant calibration error - review course design'
            else 'Course difficulty appropriately calibrated'
        end as calibration_recommendation
    from composite_difficulty cd
),

department_difficulty_patterns as (
    select
        department_name,
        count(*) as total_courses,
        avg(assigned_difficulty) as avg_assigned_difficulty,
        avg(calculated_difficulty) as avg_calculated_difficulty,
        avg(difficulty_calibration_error) as avg_calibration_error,
        count(case when calibration_status = 'Well Calibrated' then 1 end) as well_calibrated_courses,
        count(case when difficulty_assessment like '%Harder%' then 1 end) as harder_than_expected_courses,
        count(case when difficulty_assessment like '%Easier%' then 1 end) as easier_than_expected_courses,
        round(
            count(case when calibration_status = 'Well Calibrated' then 1 end) * 100.0 / count(*), 2
        ) as calibration_accuracy_rate
    from calibration_assessment
    group by department_name
),

final_analysis as (
    select
        ca.*,
        ddp.avg_assigned_difficulty as dept_avg_assigned_difficulty,
        ddp.avg_calculated_difficulty as dept_avg_calculated_difficulty,
        ddp.calibration_accuracy_rate as dept_calibration_accuracy,
        case
            when ca.calculated_difficulty > ddp.avg_calculated_difficulty + 1 then 'Above Department Average Difficulty'
            when ca.calculated_difficulty < ddp.avg_calculated_difficulty - 1 then 'Below Department Average Difficulty'
            else 'Near Department Average Difficulty'
        end as relative_difficulty_in_department,
        
        -- Overall course health score
        round(
            (case when calibration_status = 'Well Calibrated' then 25
                  when calibration_status = 'Moderately Calibrated' then 20
                  when calibration_status = 'Poorly Calibrated' then 10
                  else 5 end) +
            (case when pass_rate >= 80 then 25
                  when pass_rate >= 70 then 20
                  when pass_rate >= 60 then 15
                  else 10 end) +
            (case when withdrawal_rate <= 10 then 25
                  when withdrawal_rate <= 15 then 20
                  when withdrawal_rate <= 20 then 15
                  else 10 end) +
            (case when avg_attendance >= 85 then 25
                  when avg_attendance >= 75 then 20
                  when avg_attendance >= 65 then 15
                  else 10 end), 0
        ) as course_health_score
    from calibration_assessment ca
    left join department_difficulty_patterns ddp on ca.department_name = ddp.department_name
)

select * from final_analysis
order by difficulty_calibration_error desc, course_health_score asc