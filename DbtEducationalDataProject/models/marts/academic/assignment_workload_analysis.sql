{{ config(materialized='table') }}

with assignment_workload as (
    select
        sem.semester_id,
        sem.semester_name,
        sem.academic_year,
        sem.semester_type,
        c.course_id,
        c.course_code,
        c.course_name,
        c.credits,
        c.difficulty_level,
        d.department_name,
        a.assignment_id,
        a.assignment_name,
        a.assignment_type,
        a.assignment_category,
        a.due_date,
        a.max_points,
        a.weight_percentage,
        extract(week from a.due_date) as due_week,
        extract(month from a.due_date) as due_month,
        ap.total_submissions,
        ap.avg_percentage_score,
        ap.late_submission_rate,
        ap.avg_score,
        case
            when extract(dow from a.due_date) in (0, 6) then 'Weekend'
            else 'Weekday'
        end as due_day_type
    from {{ ref('stg_semesters') }} sem
    inner join {{ ref('stg_assignments') }} a on sem.semester_id = a.semester_id
    inner join {{ ref('stg_courses') }} c on a.course_id = c.course_id
    inner join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    left join {{ ref('int_assignment_performance') }} ap on a.assignment_id = ap.assignment_id
),

semester_workload_analysis as (
    select
        semester_id,
        semester_name,
        academic_year,
        semester_type,
        count(distinct assignment_id) as total_assignments,
        count(distinct course_id) as courses_with_assignments,
        sum(max_points) as total_possible_points,
        avg(max_points) as avg_assignment_points,
        sum(weight_percentage) as total_weight_percentage,
        avg(weight_percentage) as avg_assignment_weight,
        count(case when assignment_category = 'Assessment' then 1 end) as exam_count,
        count(case when assignment_category = 'Project' then 1 end) as project_count,
        count(case when assignment_category = 'Homework' then 1 end) as homework_count,
        count(case when assignment_category = 'Quiz' then 1 end) as quiz_count,
        count(case when due_day_type = 'Weekend' then 1 end) as weekend_due_assignments,
        avg(avg_percentage_score) as semester_avg_score,
        avg(late_submission_rate) as semester_late_rate
    from assignment_workload
    group by semester_id, semester_name, academic_year, semester_type
),

course_workload_analysis as (
    select
        course_id,
        course_code,
        course_name,
        credits,
        difficulty_level,
        department_name,
        count(distinct assignment_id) as assignments_per_course,
        sum(max_points) as total_points_possible,
        avg(max_points) as avg_points_per_assignment,
        sum(weight_percentage) as total_course_weight,
        round(count(distinct assignment_id)::numeric / credits, 2) as assignments_per_credit,
        round(sum(max_points)::numeric / credits, 2) as points_per_credit,
        count(case when assignment_category = 'Assessment' then 1 end) as course_exams,
        count(case when assignment_category = 'Project' then 1 end) as course_projects,
        count(case when assignment_category = 'Homework' then 1 end) as course_homework,
        avg(avg_percentage_score) as course_avg_performance,
        avg(late_submission_rate) as course_late_rate
    from assignment_workload
    group by course_id, course_code, course_name, credits, difficulty_level, department_name
),

weekly_workload_distribution as (
    select
        semester_id,
        semester_name,
        due_week,
        count(distinct assignment_id) as assignments_due_this_week,
        sum(max_points) as total_points_due_this_week,
        count(distinct course_id) as courses_with_assignments_due,
        avg(weight_percentage) as avg_weight_this_week
    from assignment_workload
    where due_week is not null
    group by semester_id, semester_name, due_week
),

workload_intensity as (
    select
        swa.*,
        cwa.assignments_per_course,
        cwa.assignments_per_credit,
        cwa.points_per_credit,
        www.max_weekly_assignments,
        www.max_weekly_points,
        www.avg_weekly_assignments,
        case
            when swa.total_assignments >= 100 then 'Very High Workload'
            when swa.total_assignments >= 75 then 'High Workload'
            when swa.total_assignments >= 50 then 'Moderate Workload'
            when swa.total_assignments >= 25 then 'Light Workload'
            else 'Very Light Workload'
        end as semester_workload_category,
        case
            when www.max_weekly_assignments >= 15 then 'Overwhelming Weeks'
            when www.max_weekly_assignments >= 10 then 'Heavy Weeks'
            when www.max_weekly_assignments >= 7 then 'Busy Weeks'
            else 'Manageable Weeks'
        end as peak_week_intensity,
        round(swa.total_assignments::numeric / 16, 2) as avg_assignments_per_week,  -- Assuming 16-week semester
        case
            when swa.semester_late_rate >= 25 then 'High Stress Semester'
            when swa.semester_late_rate >= 15 then 'Moderate Stress Semester'
            when swa.semester_late_rate >= 10 then 'Low Stress Semester'
            else 'Well-Managed Semester'
        end as stress_indicator
    from semester_workload_analysis swa
    left join (
        select
            course_id,
            avg(assignments_per_course) as assignments_per_course,
            avg(assignments_per_credit) as assignments_per_credit,
            avg(points_per_credit) as points_per_credit
        from course_workload_analysis
        group by course_id
    ) cwa on 1=1  -- Cross join for semester-level aggregation
    left join (
        select
            semester_id,
            max(assignments_due_this_week) as max_weekly_assignments,
            max(total_points_due_this_week) as max_weekly_points,
            avg(assignments_due_this_week) as avg_weekly_assignments
        from weekly_workload_distribution
        group by semester_id
    ) www on swa.semester_id = www.semester_id
)

select * from workload_intensity