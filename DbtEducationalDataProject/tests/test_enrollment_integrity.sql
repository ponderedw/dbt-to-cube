-- Test to ensure enrollment dates are logical
select *
from {{ ref('stg_enrollments') }} e
join {{ ref('stg_semesters') }} s on e.semester_id = s.semester_id
where e.enrollment_date > s.end_date 
   or (e.completion_date is not null and e.completion_date < e.enrollment_date)