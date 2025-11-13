{{ config(materialized='table') }}

with instructor_metrics as (
    select
        f.faculty_id,
        f.full_name,
        f.position,
        f.department_name,
        f.years_of_service,
        f.salary,
        f.unique_courses_taught,
        f.total_students_taught,
        f.avg_class_attendance,
        f.teaching_load_category,
        fsi.student_success_rate,
        fsi.avg_grade_given,
        fsi.grade_consistency,
        fsi.avg_incoming_student_gpa,
        fsi.teaching_effectiveness_category,
        fsi.student_engagement_level,
        fsi.grading_consistency_level,
        ap.avg_percentage_score as avg_assignment_performance,
        ap.late_submission_rate as avg_late_submission_rate,
        ap.grading_completion_rate as avg_grading_completion_rate
    from {{ ref('int_faculty_teaching_load') }} f
    left join {{ ref('int_faculty_student_interactions') }} fsi 
        on f.faculty_id = fsi.faculty_id
    left join (
        select
            course_id,
            avg(avg_percentage_score) as avg_percentage_score,
            avg(late_submission_rate) as late_submission_rate,
            avg(grading_completion_rate) as grading_completion_rate
        from {{ ref('int_assignment_performance') }}
        group by course_id
    ) ap on f.faculty_id = ap.course_id  -- Simplified for this example
),

performance_scoring as (
    select
        *,
        -- Teaching effectiveness score (0-100)
        round(
            (case 
                when student_success_rate >= 90 then 25
                when student_success_rate >= 80 then 20
                when student_success_rate >= 70 then 15
                when student_success_rate >= 60 then 10
                else 5
            end +
            case 
                when avg_class_attendance >= 95 then 25
                when avg_class_attendance >= 85 then 20
                when avg_class_attendance >= 75 then 15
                when avg_class_attendance >= 65 then 10
                else 5
            end +
            case 
                when grade_consistency <= 0.5 then 25
                when grade_consistency <= 1.0 then 20
                when grade_consistency <= 1.5 then 15
                when grade_consistency <= 2.0 then 10
                else 5
            end +
            case 
                when avg_grading_completion_rate >= 95 then 25
                when avg_grading_completion_rate >= 85 then 20
                when avg_grading_completion_rate >= 75 then 15
                when avg_grading_completion_rate >= 65 then 10
                else 5
            end), 0
        ) as effectiveness_score,
        
        -- Student impact score based on numbers taught and success
        round(
            (total_students_taught * student_success_rate / 100), 0
        ) as student_impact_score,
        
        -- Experience factor
        case
            when years_of_service >= 15 then 'Veteran'
            when years_of_service >= 10 then 'Senior'
            when years_of_service >= 5 then 'Experienced'
            else 'Junior'
        end as experience_level,
        
        -- Workload efficiency
        round(
            student_success_rate / nullif(unique_courses_taught, 0), 2
        ) as success_per_course_ratio
    from instructor_metrics
),

department_medians as (
    select
        department_name,
        percentile_cont(0.5) within group (order by effectiveness_score) as dept_median_effectiveness
    from performance_scoring
    group by department_name
),

peer_comparisons as (
    select
        ps.*,
        avg(effectiveness_score) over (partition by ps.department_name) as dept_avg_effectiveness,
        avg(student_impact_score) over (partition by ps.department_name) as dept_avg_impact,
        avg(student_success_rate) over (partition by ps.department_name) as dept_avg_success_rate,
        avg(total_students_taught) over (partition by ps.department_name) as dept_avg_students_taught,
        avg(effectiveness_score) over (partition by position) as position_avg_effectiveness,
        avg(student_impact_score) over (partition by position) as position_avg_impact,
        dm.dept_median_effectiveness,
        row_number() over (partition by ps.department_name order by effectiveness_score desc) as dept_effectiveness_rank,
        row_number() over (partition by position order by effectiveness_score desc) as position_effectiveness_rank,
        row_number() over (order by effectiveness_score desc) as overall_effectiveness_rank
    from performance_scoring ps
    left join department_medians dm on ps.department_name = dm.department_name
),

final_scorecard as (
    select
        pc.*,
        case
            when effectiveness_score >= 90 then 'Outstanding'
            when effectiveness_score >= 80 then 'Excellent'
            when effectiveness_score >= 70 then 'Good'
            when effectiveness_score >= 60 then 'Satisfactory'
            else 'Needs Improvement'
        end as overall_performance_rating,
        
        case
            when dept_effectiveness_rank <= 3 then 'Top Performer in Department'
            when dept_effectiveness_rank <= dept_avg_effectiveness * 0.25 then 'Above Average in Department'
            when dept_effectiveness_rank <= dept_avg_effectiveness * 0.75 then 'Average in Department'
            else 'Below Average in Department'
        end as departmental_standing,
        
        case
            when effectiveness_score > dept_avg_effectiveness * 1.2 then 'Significantly Above Department Average'
            when effectiveness_score > dept_avg_effectiveness * 1.1 then 'Above Department Average'
            when effectiveness_score between dept_avg_effectiveness * 0.9 and dept_avg_effectiveness * 1.1 then 'Near Department Average'
            when effectiveness_score > dept_avg_effectiveness * 0.8 then 'Below Department Average'
            else 'Significantly Below Department Average'
        end as performance_vs_peers,
        
        -- Recommendations
        case
            when effectiveness_score < 60 and avg_class_attendance < 75 then 'Focus on student engagement strategies'
            when effectiveness_score < 60 and student_success_rate < 70 then 'Review grading standards and course difficulty'
            when effectiveness_score < 60 and grade_consistency > 2.0 then 'Work on grading consistency'
            when effectiveness_score >= 80 then 'Mentor other faculty members'
            else 'Continue professional development'
        end as improvement_recommendations,
        
        -- Recognition eligibility
        case
            when effectiveness_score >= 90 and student_impact_score >= 150 then 'Eligible for Teaching Excellence Award'
            when effectiveness_score >= 85 and years_of_service >= 10 then 'Eligible for Veteran Educator Recognition'
            when effectiveness_score >= 80 and experience_level = 'Junior' then 'Eligible for Rising Star Award'
            else 'Standard Recognition'
        end as award_eligibility
    from peer_comparisons pc
)

select * from final_scorecard
order by effectiveness_score desc