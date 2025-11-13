{{ config(materialized='table') }}

with course_details as (
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.description,
        c.credits,
        c.difficulty_level,
        c.difficulty_description,
        c.credit_category,
        d.department_name,
        d.department_code,
        d.department_size,
        prereq.course_code as prerequisite_course,
        prereq.course_name as prerequisite_name,
        cpm.total_enrollments,
        cpm.unique_students,
        cpm.semesters_offered,
        cpm.avg_grade_points,
        cpm.avg_attendance,
        cpm.pass_rate,
        cpm.withdrawal_rate,
        cpm.excellent_grades,
        cpm.good_grades,
        cpm.satisfactory_grades,
        cpm.poor_grades,
        cpm.failing_grades,
        case
            when cpm.pass_rate >= 90 then 'High Success Rate'
            when cpm.pass_rate >= 75 then 'Good Success Rate'
            when cpm.pass_rate >= 60 then 'Moderate Success Rate'
            else 'Low Success Rate'
        end as success_category,
        case
            when cpm.withdrawal_rate >= 20 then 'High Dropout Risk'
            when cpm.withdrawal_rate >= 10 then 'Moderate Dropout Risk'
            when cpm.withdrawal_rate >= 5 then 'Low Dropout Risk'
            else 'Minimal Dropout Risk'
        end as dropout_risk,
        case
            when cpm.avg_attendance >= 95 then 'Excellent Engagement'
            when cpm.avg_attendance >= 85 then 'Good Engagement'
            when cpm.avg_attendance >= 75 then 'Fair Engagement'
            else 'Poor Engagement'
        end as engagement_level
    from {{ ref('stg_courses') }} c
    left join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('stg_courses') }} prereq on c.prerequisite_course_id = prereq.course_id
    left join {{ ref('int_course_performance_metrics') }} cpm on c.course_id = cpm.course_id
)

select * from course_details