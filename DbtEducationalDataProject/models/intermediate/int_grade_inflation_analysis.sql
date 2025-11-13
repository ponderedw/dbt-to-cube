{{ config(materialized='view') }}

with historical_grades as (
    select
        c.course_id,
        c.course_code,
        c.course_name,
        c.department_id,
        c.difficulty_level,
        d.department_name,
        e.semester_id,
        e.grade,
        e.grade_points,
        sem.academic_year,
        sem.semester_type,
        extract(year from sem.start_date) as year,
        f.faculty_id,
        f.full_name,
        f.years_of_service,
        case
            when e.grade in ('A+', 'A', 'A-') then 'A Range'
            when e.grade in ('B+', 'B', 'B-') then 'B Range'
            when e.grade in ('C+', 'C', 'C-') then 'C Range'
            when e.grade in ('D+', 'D', 'D-') then 'D Range'
            when e.grade = 'F' then 'F'
            else 'Other'
        end as grade_range
    from {{ ref('stg_enrollments') }} e
    inner join {{ ref('stg_courses') }} c on e.course_id = c.course_id
    inner join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    inner join {{ ref('stg_semesters') }} sem on e.semester_id = sem.semester_id
    left join {{ ref('stg_class_sessions') }} cs on c.course_id = cs.course_id and e.semester_id = cs.semester_id
    left join {{ ref('stg_faculty') }} f on cs.faculty_id = f.faculty_id
    where e.grade is not null and e.grade != 'W'
),

yearly_grade_trends as (
    select
        year,
        course_id,
        course_code,
        course_name,
        department_name,
        difficulty_level,
        count(*) as total_grades,
        avg(grade_points) as avg_gpa,
        count(case when grade_range = 'A Range' then 1 end) as a_grades,
        count(case when grade_range = 'B Range' then 1 end) as b_grades,
        count(case when grade_range = 'C Range' then 1 end) as c_grades,
        count(case when grade_range = 'D Range' then 1 end) as d_grades,
        count(case when grade_range = 'F' then 1 end) as f_grades,
        round(count(case when grade_range = 'A Range' then 1 end) * 100.0 / count(*), 2) as a_percentage,
        round(count(case when grade_range = 'B Range' then 1 end) * 100.0 / count(*), 2) as b_percentage,
        round(count(case when grade_range = 'C Range' then 1 end) * 100.0 / count(*), 2) as c_percentage,
        round(count(case when grade_range in ('A Range', 'B Range') then 1 end) * 100.0 / count(*), 2) as ab_percentage
    from historical_grades
    group by year, course_id, course_code, course_name, department_name, difficulty_level
    having count(*) >= 10  -- Only courses with sufficient enrollment
),

inflation_analysis as (
    select
        ygt.*,
        lag(avg_gpa, 1) over (partition by course_id order by year) as prev_year_gpa,
        lag(a_percentage, 1) over (partition by course_id order by year) as prev_year_a_percentage,
        lag(ab_percentage, 1) over (partition by course_id order by year) as prev_year_ab_percentage,
        avg_gpa - lag(avg_gpa, 1) over (partition by course_id order by year) as gpa_change,
        a_percentage - lag(a_percentage, 1) over (partition by course_id order by year) as a_percentage_change,
        ab_percentage - lag(ab_percentage, 1) over (partition by course_id order by year) as ab_percentage_change,
        first_value(avg_gpa) over (partition by course_id order by year) as baseline_gpa,
        first_value(a_percentage) over (partition by course_id order by year) as baseline_a_percentage,
        avg_gpa - first_value(avg_gpa) over (partition by course_id order by year) as cumulative_gpa_change,
        a_percentage - first_value(a_percentage) over (partition by course_id order by year) as cumulative_a_change
    from yearly_grade_trends ygt
),

department_trends as (
    select
        department_name,
        year,
        avg(avg_gpa) as dept_avg_gpa,
        avg(a_percentage) as dept_avg_a_percentage,
        avg(ab_percentage) as dept_avg_ab_percentage,
        count(distinct course_id) as courses_analyzed
    from yearly_grade_trends
    group by department_name, year
),

faculty_grade_patterns as (
    select
        faculty_id,
        full_name,
        years_of_service,
        department_name,
        count(distinct course_id) as courses_taught,
        avg(grade_points) as faculty_avg_grade,
        round(count(case when grade_range = 'A Range' then 1 end) * 100.0 / count(*), 2) as faculty_a_percentage,
        round(count(case when grade_range = 'F' then 1 end) * 100.0 / count(*), 2) as faculty_f_percentage,
        stddev(grade_points) as faculty_grade_variance
    from historical_grades
    where faculty_id is not null
    group by faculty_id, full_name, years_of_service, department_name
    having count(*) >= 20  -- Only faculty with sufficient grading history
),

inflation_indicators as (
    select
        ia.*,
        dt.dept_avg_gpa,
        dt.dept_avg_a_percentage,
        case
            when cumulative_gpa_change >= 0.5 then 'Significant Grade Inflation'
            when cumulative_gpa_change >= 0.3 then 'Moderate Grade Inflation'
            when cumulative_gpa_change >= 0.1 then 'Mild Grade Inflation'
            when cumulative_gpa_change >= -0.1 then 'Stable Grading'
            when cumulative_gpa_change >= -0.3 then 'Mild Grade Deflation'
            else 'Significant Grade Deflation'
        end as inflation_category,
        case
            when cumulative_a_change >= 20 then 'High A Grade Inflation'
            when cumulative_a_change >= 10 then 'Moderate A Grade Inflation'
            when cumulative_a_change >= 5 then 'Mild A Grade Inflation'
            when cumulative_a_change >= -5 then 'Stable A Grading'
            else 'A Grade Deflation'
        end as a_grade_inflation_category,
        case
            when gpa_change >= 0.2 then 'Significant Year-over-Year Increase'
            when gpa_change >= 0.1 then 'Moderate Year-over-Year Increase'
            when gpa_change >= 0.05 then 'Slight Year-over-Year Increase'
            when gpa_change >= -0.05 then 'Stable Year-over-Year'
            when gpa_change >= -0.1 then 'Slight Year-over-Year Decrease'
            else 'Significant Year-over-Year Decrease'
        end as annual_trend_category
    from inflation_analysis ia
    left join department_trends dt on ia.department_name = dt.department_name and ia.year = dt.year
)

select 
    ii.*,
    fgp.faculty_avg_grade,
    fgp.faculty_a_percentage,
    fgp.faculty_grade_variance,
    case
        when ii.avg_gpa > ii.dept_avg_gpa * 1.1 then 'Above Department Average'
        when ii.avg_gpa < ii.dept_avg_gpa * 0.9 then 'Below Department Average'
        else 'Near Department Average'
    end as course_vs_department_grading
from inflation_indicators ii
left join faculty_grade_patterns fgp on ii.course_id = fgp.faculty_id  -- Simplified join for this example