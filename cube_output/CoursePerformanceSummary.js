cube(`CoursePerformanceSummary`, {
  sql: `SELECT * FROM public.course_performance_summary`,
  
  dimensions: {
    course_id: {
      sql: `course_id`,
      type: `number`,
      title: 'Unique identifier for the course'
    },

    course_code: {
      sql: `course_code`,
      type: `string`,
      title: 'Course code (e.g., CS101, MATH201)'
    },

    course_name: {
      sql: `course_name`,
      type: `string`,
      title: 'Full name of the course'
    },

    credits: {
      sql: `credits`,
      type: `number`,
      title: 'Number of credit hours for the course'
    },

    difficulty_level: {
      sql: `difficulty_level`,
      type: `number`,
      title: 'Course difficulty level (1-5 scale)'
    },

    department_name: {
      sql: `department_name`,
      type: `string`,
      title: 'Academic department offering the course'
    },

    semester_name: {
      sql: `semester_name`,
      type: `string`,
      title: 'Semester when the course was offered'
    },

    academic_year: {
      sql: `academic_year`,
      type: `string`,
      title: 'Academic year of the course offering'
    },

    semester_start_date: {
      sql: `semester_start_date`,
      type: `time`,
      title: 'Start date of the semester'
    },

    semester_end_date: {
      sql: `semester_end_date`,
      type: `time`,
      title: 'End date of the semester'
    },

    total_enrollments: {
      sql: `total_enrollments`,
      type: `number`,
      title: 'Total number of students enrolled in the course'
    },

    avg_grade_points: {
      sql: `avg_grade_points`,
      type: `number`,
      title: 'Average grade points achieved by students'
    },

    avg_attendance: {
      sql: `avg_attendance`,
      type: `number`,
      title: 'Average attendance percentage for the course'
    },

    excellent_performance: {
      sql: `excellent_performance`,
      type: `number`,
      title: 'Number of students with excellent performance (3.5+ GPA)'
    },

    passing_grades: {
      sql: `passing_grades`,
      type: `number`,
      title: 'Number of students with passing grades (2.0+ GPA)'
    },

    instructor_name: {
      sql: `instructor_name`,
      type: `string`,
      title: 'Name of the course instructor'
    },

    instructor_position: {
      sql: `instructor_position`,
      type: `string`,
      title: 'Academic position of the instructor'
    },

    pass_rate_percentage: {
      sql: `pass_rate_percentage`,
      type: `number`,
      title: 'Percentage of students who passed the course'
    },

    excellence_rate_percentage: {
      sql: `excellence_rate_percentage`,
      type: `number`,
      title: 'Percentage of students with excellent performance'
    },

    performance_category: {
      sql: `performance_category`,
      type: `string`,
      title: 'Overall performance category for the course'
    }
  },
  
  measures: {
    average_course_gpa: {
      type: `avg`,
      sql: `${avg_grade_points}`,
      title: 'Average Course Gpa'
    },

    course_pass_rate: {
      type: `avg`,
      sql: `${pass_rate_percentage} / 100`,
      title: 'Course Pass Rate'
    },

    total_course_enrollments: {
      type: `sum`,
      sql: `${total_enrollments}`,
      title: 'Total Course Enrollments'
    },

    student_engagement_score: {
      type: `avg`,
      sql: `(${avg_attendance} * 0.6 + ${avg_grade_points} * 25)`,
      title: 'Student Engagement Score'
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
