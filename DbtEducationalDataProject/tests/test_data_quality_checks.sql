-- Test to ensure no student has impossible GPA values
select *
from {{ ref('stg_students') }}
where gpa < 0.0 or gpa > 4.0