{{ config(materialized='table') }}

-- Synthetic attendance metrics derived from enrollment data.
-- This model demonstrates the attendance-tracking semantic pattern
-- (filters, format, foreign-key joins) using the existing staging models.
WITH enrollment_base AS (
    SELECT
        e.student_id,
        e.course_id  AS section_id,
        s.semester_id,
        s.start_date AS semester_start_date,
        s.semester_name,
        s.semester_type,
        s.semester_status,
        s.academic_year,
        d.department_name AS school_name,

        -- Approximate gradespan from department name (demo only)
        CASE
            WHEN d.department_name IN ('Mathematics', 'Sciences', 'Computer Science')
                THEN 'STEM'
            ELSE 'Liberal Arts'
        END AS gradespan,

        -- ODP flag: students with grade_points below 1.0 are treated as "ODP" for demo
        CASE WHEN e.grade_points < 1.0 THEN 1 ELSE 0 END AS is_odp_student,

        -- Synthetic attendance metrics derived from attendance_percentage
        100                                                     AS days_enrolled,
        ROUND((e.attendance_percentage)::numeric, 0)            AS days_present,
        ROUND((100 - e.attendance_percentage)::numeric, 0)      AS days_absent,
        ROUND((100 - e.attendance_percentage) * 0.3, 0)         AS days_tardy

    FROM {{ ref('stg_enrollments') }} e
    LEFT JOIN {{ ref('stg_semesters') }} s ON e.semester_id = s.semester_id
    LEFT JOIN {{ ref('stg_courses') }}   c ON e.course_id   = c.course_id
    LEFT JOIN {{ ref('stg_departments') }} d ON c.department_id = d.department_id
    WHERE e.grade_points IS NOT NULL
),

attendance_summary AS (
    SELECT
        student_id,
        section_id,
        semester_id,
        semester_start_date,
        semester_name,
        semester_type,
        semester_status,
        academic_year,
        school_name,
        gradespan,
        is_odp_student,

        SUM(days_enrolled)   AS days_enrolled,
        SUM(days_present)    AS days_present,
        SUM(days_absent)     AS days_absent,
        SUM(days_tardy)      AS days_tardy
    FROM enrollment_base
    GROUP BY
        student_id, section_id, semester_id, semester_start_date,
        semester_name, semester_type, semester_status, academic_year,
        school_name, gradespan, is_odp_student
),

final AS (
    SELECT
        *,
        CASE WHEN days_enrolled > 0
            THEN ROUND(days_present::NUMERIC / days_enrolled, 4)
            ELSE 0
        END AS attendance_rate,
        CASE WHEN days_enrolled > 0
            THEN ROUND(days_absent::NUMERIC / days_enrolled, 4)
            ELSE 0
        END AS absence_rate
    FROM attendance_summary
)

SELECT * FROM final
