cube(`SemanticCoursePerformance`, {
  sql: `SELECT * FROM public.course_performance_summary`,
  
  dimensions: {
    course_code: {
      sql: `course_code`,
      type: `string`,
      title: `Course Code`,
      description: `Short code identifying the course (e.g. CS101, MATH201).`
    },

    course_name: {
      sql: `course_name`,
      type: `string`,
      title: `Course Name`,
      description: `Full name of the course.`
    },

    department_name: {
      sql: `department_name`,
      type: `string`,
      title: `Department`,
      description: `Academic department offering the course.`
    },

    semester_name: {
      sql: `semester_name`,
      type: `string`,
      title: `Semester`,
      description: `Semester in which the course was offered.`
    },

    academic_year: {
      sql: `academic_year`,
      type: `string`,
      title: `Academic Year`,
      description: `Academic year of the course offering (e.g. 2023-2024).`
    },

    instructor_name: {
      sql: `instructor_name`,
      type: `string`,
      title: `Instructor`,
      description: `Full name of the course instructor.`
    },

    performance_category: {
      sql: `performance_category`,
      type: `string`,
      title: `Performance Category`,
      description: `Overall performance tier for the course (e.g. High, Medium, Low).`
    },

    semester_start_date: {
      sql: `semester_start_date`,
      type: `time`,
      title: `Semester Start Date`,
      description: `Date the semester began; used as the aggregation time dimension.`
    }
  },
  
  measures: {
    course_enrollment_count: {
      type: `sum`,
      sql: `total_enrollments`,
      title: `Course Enrollment Count`,
      description: `Total student enrolments across all course offerings.`
    },

    avg_course_gpa: {
      type: `avg`,
      sql: `avg_grade_points`,
      title: `Avg Course GPA`,
      description: `Average grade point average across course offerings.`
    },

    avg_pass_rate: {
      type: `avg`,
      sql: `pass_rate_percentage`,
      title: `Avg Pass Rate`,
      description: `Average pass-rate percentage across course offerings.`
    },

    avg_engagement_score: {
      type: `avg`,
      sql: `(avg_attendance * 0.6 + avg_grade_points * 25)`,
      title: `Avg Engagement Score`,
      description: `Average composite engagement score (60% attendance + 40% GPA component).`
    },

    gpa_pass_quality_index: {
      type: `number`,
      sql: `${average_course_gpa} * ${average_pass_rate} / 100`,
      title: `GPA–Pass Quality Index`,
      description: `Composite quality score: GPA normalised to 0-100 multiplied by pass rate, divided by 100.`
    },

    average_course_gpa: {
      type: `avg`,
      sql: `avg_grade_points`,
      title: `Average Course GPA`,
      description: `Mean grade point average across all course offerings.`
    },

    average_engagement_score: {
      type: `avg`,
      sql: `(avg_attendance * 0.6 + avg_grade_points * 25)`,
      title: `Average Engagement Score`,
      description: `Mean composite engagement score across course offerings.`
    },

    average_pass_rate: {
      type: `avg`,
      sql: `pass_rate_percentage`,
      title: `Average Pass Rate`,
      description: `Mean pass-rate percentage across all course offerings.`
    },

    cumulative_enrollments: {
      type: `sum`,
      sql: `total_enrollments`,
      title: `Cumulative Enrollments`,
      description: `Running total of course enrolments over time.`
    },

    total_course_enrollments: {
      type: `sum`,
      sql: `total_enrollments`,
      title: `Total Course Enrollments`,
      description: `Total number of student enrolments across all course offerings.`
    }
  },
  
  pre_aggregations: {
    course_by_department_monthly: {
      type: `rollup`,
      measures: [CUBE.course_enrollment_count, CUBE.total_course_enrollments, CUBE.cumulative_enrollments],
      dimensions: [CUBE.department_name, CUBE.performance_category],
      time_dimension: CUBE.semester_start_date,
      granularity: `month`,
      refresh_key: {
        every: `1 day`
      }
    }
  }
});
