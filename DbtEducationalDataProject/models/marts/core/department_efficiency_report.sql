{{ config(materialized='table') }}

with department_efficiency as (
    select
        da.department_id,
        da.department_name,
        da.department_code,
        da.budget,
        da.budget_millions,
        da.department_size,
        da.building_location,
        da.faculty_count,
        da.course_count,
        da.student_count,
        da.total_enrollments,
        da.avg_faculty_salary,
        da.total_faculty_salary_cost,
        da.avg_student_gpa,
        da.total_credit_hours_offered,
        da.professor_count,
        da.associate_professor_count,
        da.assistant_professor_count,
        da.avg_course_difficulty,
        da.budget_per_faculty,
        da.budget_per_student,
        da.salary_cost_percentage,
        da.student_faculty_ratio,
        da.courses_per_faculty,
        da.avg_enrollment_per_course,
        da.department_scale,
        da.ratio_category,
        avg(cpm.pass_rate) as dept_avg_pass_rate,
        avg(cpm.withdrawal_rate) as dept_avg_withdrawal_rate,
        avg(cpm.avg_attendance) as dept_avg_attendance,
        count(case when cpm.pass_rate >= 80 then 1 end) as high_performing_courses,
        count(case when cpm.withdrawal_rate >= 15 then 1 end) as problematic_courses,
        case
            when da.salary_cost_percentage <= 60 then 'Efficient Budget Management'
            when da.salary_cost_percentage <= 75 then 'Moderate Budget Management'
            when da.salary_cost_percentage <= 90 then 'Tight Budget Management'
            else 'Over Budget'
        end as budget_efficiency,
        case
            when avg(cpm.pass_rate) >= 85 then 'Excellent Academic Performance'
            when avg(cpm.pass_rate) >= 75 then 'Good Academic Performance'
            when avg(cpm.pass_rate) >= 65 then 'Fair Academic Performance'
            else 'Poor Academic Performance'
        end as academic_performance_category,
        round(da.total_enrollments::numeric / nullif(da.budget, 0) * 100000, 2) as enrollments_per_100k_budget,
        round(da.student_count::numeric / nullif(da.budget, 0) * 100000, 2) as students_per_100k_budget
    from {{ ref('int_department_analytics') }} da
    left join {{ ref('int_course_performance_metrics') }} cpm on da.department_id = cpm.course_id  -- This assumes course_id maps to department for simplicity
    group by 
        da.department_id, da.department_name, da.department_code, da.budget, 
        da.budget_millions, da.department_size, da.building_location, da.faculty_count, 
        da.course_count, da.student_count, da.total_enrollments, da.avg_faculty_salary, 
        da.total_faculty_salary_cost, da.avg_student_gpa, da.total_credit_hours_offered, 
        da.professor_count, da.associate_professor_count, da.assistant_professor_count, 
        da.avg_course_difficulty, da.budget_per_faculty, da.budget_per_student, 
        da.salary_cost_percentage, da.student_faculty_ratio, da.courses_per_faculty, 
        da.avg_enrollment_per_course, da.department_scale, da.ratio_category
)

select * from department_efficiency