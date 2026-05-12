cube(`CoursePerformanceSummary`, {
  sql: `SELECT * FROM public.course_performance_summary`,
  
  dimensions: {
    course_id: {
      sql: `course_id`,
      type: `number`,
      title: `Course ID`,
      description: `Unique identifier for the course`
    },

    course_code: {
      sql: `course_code`,
      type: `string`,
      title: `Course Code`,
      description: `Course code (e.g., CS101, MATH201)`
    },

    course_name: {
      sql: `course_name`,
      type: `string`,
      title: `Course Name`,
      description: `Full name of the course`
    },

    credits: {
      sql: `credits`,
      type: `number`,
      title: `Credit Hours`,
      description: `Number of credit hours for the course`
    },

    difficulty_level: {
      sql: `difficulty_level`,
      type: `number`,
      title: `Difficulty Level`,
      description: `Course difficulty level (1-5 scale)`
    },

    department_name: {
      sql: `department_name`,
      type: `string`,
      title: `Department`,
      description: `Academic department offering the course`
    },

    semester_name: {
      sql: `semester_name`,
      type: `string`,
      title: `Semester`,
      description: `Semester when the course was offered`
    },

    academic_year: {
      sql: `academic_year`,
      type: `string`,
      title: `Academic Year`,
      description: `Academic year of the course offering`
    },

    semester_start_date: {
      sql: `semester_start_date`,
      type: `time`,
      title: `Semester Start`,
      description: `Start date of the semester`
    },

    semester_end_date: {
      sql: `semester_end_date`,
      type: `time`,
      title: `Semester End`,
      description: `End date of the semester`
    },

    instructor_name: {
      sql: `instructor_name`,
      type: `string`,
      title: `Instructor`,
      description: `Name of the course instructor`
    },

    instructor_position: {
      sql: `instructor_position`,
      type: `string`,
      title: `Instructor Position`,
      description: `Academic position of the instructor`
    },

    performance_category: {
      sql: `performance_category`,
      type: `string`,
      title: `Performance Category`,
      description: `Overall performance category for the course`
    }
  },
  
  measures: {
    average_course_gpa: {
      type: `avg`,
      sql: `avg_grade_points`,
      title: `Average Course GPA`,
      description: `Mean grade point average across all enrolled students`
    },

    course_pass_rate: {
      type: `avg`,
      sql: `pass_rate_percentage / 100`,
      title: `Course Pass Rate`,
      description: `Proportion of students achieving a passing grade (2.0+ GPA)`
    },

    total_course_enrollments: {
      type: `sum`,
      sql: `total_enrollments`,
      title: `Total Course Enrollments`,
      description: `Total number of student enrollments across all course sections`
    },

    student_engagement_score: {
      type: `avg`,
      sql: `(avg_attendance * 0.6 + avg_grade_points * 25)`,
      title: `Student Engagement Score`,
      description: `Composite score combining attendance (60%) and academic performance (40%)`
    }
  },
  
  pre_aggregations: {
    course_performance_realtime: {
      type: `rollup`,
      measures: [CUBE.average_course_gpa, CUBE.total_course_enrollments],
      dimensions: [CUBE.department_name, CUBE.semester_name],
      time_dimension: CUBE.semester_start_date,
      granularity: `month`,
      refresh_key: {
        every: `1 minute`,
        sql: `SELECT MAX(semester_end_date) FROM public.course_performance_summary`
      }
    },

    course_performance_daily: {
      type: `rollup`,
      measures: [CUBE.course_pass_rate, CUBE.student_engagement_score],
      dimensions: [CUBE.department_name],
      refresh_key: {
        every: `1 day`
      }
    },

    course_performance_hourly: {
      type: `rollup`,
      measures: [CUBE.total_course_enrollments],
      dimensions: [CUBE.performance_category],
      refresh_key: {
        every: `30 minutes`
      }
    }
  }
});
