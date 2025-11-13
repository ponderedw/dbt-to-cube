{{ config(materialized='view') }}

with student_course_connections as (
    select
        e1.student_id as student_a,
        e2.student_id as student_b,
        e1.course_id,
        e1.semester_id,
        c.course_code,
        c.course_name,
        c.difficulty_level,
        d.department_name,
        sem.semester_name,
        sem.academic_year,
        s1.full_name as student_a_name,
        s2.full_name as student_b_name,
        s1.gpa as student_a_gpa,
        s2.gpa as student_b_gpa,
        s1.major_id as student_a_major,
        s2.major_id as student_b_major,
        e1.grade_points as student_a_grade,
        e2.grade_points as student_b_grade,
        abs(e1.grade_points - e2.grade_points) as grade_difference
    from {{ ref('stg_enrollments') }} e1
    inner join {{ ref('stg_enrollments') }} e2 
        on e1.course_id = e2.course_id 
        and e1.semester_id = e2.semester_id
        and e1.student_id < e2.student_id  -- Avoid duplicates
    inner join {{ ref('stg_courses') }} c on e1.course_id = c.course_id
    inner join {{ ref('stg_departments') }} d on c.department_id = d.department_id
    inner join {{ ref('stg_semesters') }} sem on e1.semester_id = sem.semester_id
    inner join {{ ref('stg_students') }} s1 on e1.student_id = s1.student_id
    inner join {{ ref('stg_students') }} s2 on e2.student_id = s2.student_id
    where e1.enrollment_status = 'Completed' and e2.enrollment_status = 'Completed'
),

student_collaboration_strength as (
    select
        student_a,
        student_b,
        student_a_name,
        student_b_name,
        count(distinct course_id) as shared_courses,
        count(distinct semester_id) as shared_semesters,
        count(distinct department_name) as shared_departments,
        avg(difficulty_level) as avg_shared_course_difficulty,
        avg(grade_difference) as avg_grade_difference,
        corr(student_a_grade, student_b_grade) as grade_correlation,
        case when student_a_major = student_b_major then 1 else 0 end as same_major,
        abs(student_a_gpa - student_b_gpa) as gpa_difference,
        LEAST(student_a_gpa, student_b_gpa) as min_gpa,
        GREATEST(student_a_gpa, student_b_gpa) as max_gpa
    from student_course_connections
    group by 
        student_a, student_b, student_a_name, student_b_name, 
        student_a_major, student_b_major, student_a_gpa, student_b_gpa
    having count(distinct course_id) >= 2  -- Only pairs who took multiple courses together
),

collaboration_analysis as (
    select
        *,
        case
            when shared_courses >= 6 then 'Very Strong Connection'
            when shared_courses >= 4 then 'Strong Connection'
            when shared_courses >= 3 then 'Moderate Connection'
            else 'Weak Connection'
        end as connection_strength,
        
        case
            when grade_correlation >= 0.7 then 'Very Similar Performance'
            when grade_correlation >= 0.4 then 'Similar Performance'
            when grade_correlation >= 0.1 then 'Somewhat Similar Performance'
            when grade_correlation >= -0.1 then 'Unrelated Performance'
            else 'Opposite Performance Patterns'
        end as performance_similarity,
        
        case
            when avg_grade_difference <= 0.3 then 'Very Close Academic Peers'
            when avg_grade_difference <= 0.7 then 'Close Academic Peers'
            when avg_grade_difference <= 1.2 then 'Moderate Academic Difference'
            else 'Significant Academic Difference'
        end as academic_peer_level,
        
        case
            when gpa_difference <= 0.2 and same_major = 1 then 'Ideal Study Partners'
            when gpa_difference <= 0.5 and shared_departments >= 2 then 'Good Study Partners'
            when max_gpa - min_gpa >= 1.0 and same_major = 1 then 'Mentoring Opportunity'
            else 'Diverse Learning Partnership'
        end as collaboration_type
    from student_collaboration_strength scs
),

faculty_collaboration_networks as (
    select
        f1.faculty_id as faculty_a,
        f2.faculty_id as faculty_b,
        f1.full_name as faculty_a_name,
        f2.full_name as faculty_b_name,
        d1.department_name as faculty_a_dept,
        d2.department_name as faculty_b_dept,
        count(distinct cs1.course_id) as shared_teaching_opportunities,
        count(distinct cs1.semester_id) as semesters_co_teaching,
        count(distinct e.student_id) as shared_students,
        avg(e.grade_points) as avg_shared_student_performance,
        case when f1.department_id = f2.department_id then 1 else 0 end as same_department
    from {{ ref('stg_faculty') }} f1
    inner join {{ ref('stg_faculty') }} f2 on f1.faculty_id < f2.faculty_id
    inner join {{ ref('stg_departments') }} d1 on f1.department_id = d1.department_id
    inner join {{ ref('stg_departments') }} d2 on f2.department_id = d2.department_id
    inner join {{ ref('stg_class_sessions') }} cs1 on f1.faculty_id = cs1.faculty_id
    inner join {{ ref('stg_class_sessions') }} cs2 on f2.faculty_id = cs2.faculty_id
        and cs1.semester_id = cs2.semester_id
    inner join {{ ref('stg_enrollments') }} e on cs1.course_id = e.course_id 
        and cs1.semester_id = e.semester_id
    inner join {{ ref('stg_enrollments') }} e2 on cs2.course_id = e2.course_id 
        and cs2.semester_id = e2.semester_id
        and e.student_id = e2.student_id  -- Same student in both courses
    group by 
        f1.faculty_id, f2.faculty_id, f1.full_name, f2.full_name,
        d1.department_name, d2.department_name, f1.department_id, f2.department_id
    having count(distinct e.student_id) >= 3  -- Faculty who share multiple students
),

department_collaboration_metrics as (
    select
        scc.department_name,
        count(distinct ca.student_a) + count(distinct ca.student_b) as unique_students_in_collaborations,
        avg(ca.shared_courses) as avg_shared_courses_per_pair,
        count(case when ca.connection_strength in ('Strong Connection', 'Very Strong Connection') then 1 end) as strong_collaborations,
        count(case when ca.same_major = 1 then 1 end) as same_major_collaborations,
        count(case when ca.collaboration_type like '%Mentoring%' then 1 end) as mentoring_opportunities,
        round(
            count(case when ca.performance_similarity like '%Similar%' then 1 end) * 100.0 / count(*), 2
        ) as performance_similarity_rate
    from student_course_connections scc
    inner join collaboration_analysis ca 
        on scc.student_a = ca.student_a and scc.student_b = ca.student_b
    group by scc.department_name
),

network_insights as (
    select
        ca.*,
        dcm.avg_shared_courses_per_pair as dept_avg_shared_courses,
        dcm.performance_similarity_rate as dept_similarity_rate,
        case
            when ca.shared_courses > dcm.avg_shared_courses_per_pair * 1.5 then 'Above Average Collaboration'
            when ca.shared_courses < dcm.avg_shared_courses_per_pair * 0.5 then 'Below Average Collaboration'
            else 'Average Collaboration'
        end as relative_collaboration_level,
        
        -- Network value score
        round(
            (case when connection_strength = 'Very Strong Connection' then 25
                  when connection_strength = 'Strong Connection' then 20
                  when connection_strength = 'Moderate Connection' then 15
                  else 10 end) +
            (case when performance_similarity like '%Very Similar%' then 20
                  when performance_similarity like '%Similar%' then 15
                  else 10 end) +
            (case when collaboration_type like '%Ideal%' then 25
                  when collaboration_type like '%Good%' then 20
                  when collaboration_type like '%Mentoring%' then 30
                  else 15 end) +
            (case when same_major = 1 then 15 else 10 end) +
            (case when avg_shared_course_difficulty >= 4 then 15
                  when avg_shared_course_difficulty >= 3 then 10
                  else 5 end), 0
        ) as collaboration_value_score
    from collaboration_analysis ca
    left join department_collaboration_metrics dcm 
        on ca.student_a in (
            select distinct student_a from student_course_connections 
            where department_name = dcm.department_name
        )
)

select * from network_insights
order by collaboration_value_score desc