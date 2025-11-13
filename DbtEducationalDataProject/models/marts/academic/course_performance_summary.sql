{{ config(materialized='table') }}

WITH course_metrics AS (
    SELECT 
        c.course_id,
        c.course_code,
        c.course_name,
        c.credits,
        c.difficulty_level,
        d.department_name,
        s.semester_name,
        s.academic_year,
        s.start_date as semester_start_date,
        s.end_date as semester_end_date,
        
        -- Performance metrics
        COUNT(DISTINCT e.student_id) as total_enrollments,
        ROUND(AVG(e.grade_points)::numeric::numeric, 2) as avg_grade_points,
        ROUND(AVG(e.attendance_percentage)::numeric::numeric, 1) as avg_attendance,
        
        -- Success rates
        COUNT(CASE WHEN e.grade_points >= 3.5 THEN 1 END) as excellent_performance,
        COUNT(CASE WHEN e.grade_points >= 2.0 THEN 1 END) as passing_grades,
        
        -- Faculty info
        f.first_name || ' ' || f.last_name as instructor_name,
        f.position as instructor_position
        
    FROM {{ ref('stg_courses') }} c
    LEFT JOIN {{ ref('stg_enrollments') }} e ON c.course_id = e.course_id
    LEFT JOIN {{ ref('stg_departments') }} d ON c.department_id = d.department_id
    LEFT JOIN {{ ref('stg_semesters') }} s ON e.semester_id = s.semester_id
    LEFT JOIN {{ ref('stg_class_sessions') }} cs ON c.course_id = cs.course_id AND s.semester_id = cs.semester_id
    LEFT JOIN {{ ref('stg_faculty') }} f ON cs.faculty_id = f.faculty_id
    
    WHERE e.grade_points IS NOT NULL
    GROUP BY 
        c.course_id, c.course_code, c.course_name, c.credits, c.difficulty_level,
        d.department_name, s.semester_name, s.academic_year, s.start_date, s.end_date,
        f.first_name, f.last_name, f.position
),

enriched_metrics AS (
    SELECT 
        *,
        CASE 
            WHEN total_enrollments = 0 THEN 0
            ELSE ROUND(((passing_grades::FLOAT / total_enrollments) * 100)::numeric::numeric, 1)
        END as pass_rate_percentage,
        
        CASE 
            WHEN total_enrollments = 0 THEN 0
            ELSE ROUND(((excellent_performance::FLOAT / total_enrollments) * 100)::numeric::numeric, 1)
        END as excellence_rate_percentage,
        
        CASE 
            WHEN avg_grade_points >= 3.5 THEN 'High Performance'
            WHEN avg_grade_points >= 3.0 THEN 'Good Performance'
            WHEN avg_grade_points >= 2.5 THEN 'Average Performance'
            ELSE 'Needs Improvement'
        END as performance_category
        
    FROM course_metrics
)

SELECT * FROM enriched_metrics
WHERE total_enrollments > 0
ORDER BY academic_year DESC, department_name, course_code