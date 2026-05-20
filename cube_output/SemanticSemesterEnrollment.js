cube(`SemanticSemesterEnrollment`, {
  sql: `SELECT * FROM public.semester_enrollment_trends`,
  
  dimensions: {
    semester_name: {
      sql: `semester_name`,
      type: `string`,
      title: `Semester Name`,
      description: `Human-readable name of the semester (e.g. Fall 2023).`
    },

    academic_year: {
      sql: `academic_year`,
      type: `string`,
      title: `Academic Year`,
      description: `Academic year the semester belongs to (e.g. 2023-2024).`
    },

    semester_type: {
      sql: `semester_type`,
      type: `string`,
      title: `Semester Type`,
      description: `Season of the semester: Fall, Spring, or Summer.`
    },

    semester_status: {
      sql: `semester_status`,
      type: `string`,
      title: `Semester Status`,
      description: `Current status of the semester (e.g. Active, Completed).`
    },

    start_date: {
      sql: `start_date`,
      type: `time`,
      title: `Semester Start Date`,
      description: `Date the semester began; used as the aggregation time dimension.`
    },

    end_date: {
      sql: `end_date`,
      type: `time`,
      title: `Semester End Date`,
      description: `Date the semester ended.`
    }
  },
  
  measures: {
    total_semester_enrollments: {
      type: `sum`,
      sql: `total_enrollments`,
      title: `Total Semester Enrollments`,
      description: `Total number of student enrolments recorded in the semester.`
    },

    total_unique_students: {
      type: `sum`,
      sql: `unique_students`,
      title: `Total Unique Students`,
      description: `Count of distinct students enrolled in the semester.`
    },

    total_unique_courses: {
      type: `sum`,
      sql: `unique_courses`,
      title: `Total Unique Courses`,
      description: `Count of distinct courses offered in the semester.`
    },

    avg_semester_gpa: {
      type: `avg`,
      sql: `avg_semester_grade_points`,
      title: `Avg Semester GPA`,
      description: `Average grade point average across all students in the semester.`
    },

    total_deans_list_students: {
      type: `sum`,
      sql: `deans_list_students`,
      title: `Total Dean's List Students`,
      description: `Number of students who achieved Dean's List standing.`
    },

    total_probation_students: {
      type: `sum`,
      sql: `probation_students`,
      title: `Total Probation Students`,
      description: `Number of students placed on academic probation.`
    },

    average_semester_gpa: {
      type: `avg`,
      sql: `avg_semester_grade_points`,
      title: `Average Semester GPA`,
      description: `Mean grade point average across all semesters.`
    },

    deans_list_rate: {
      type: `number`,
      sql: `${total_deans_list} / NULLIF(${total_semester_headcount}, 0)`,
      title: `Dean's List Rate`,
      description: `Proportion of enrolled students achieving Dean's List standing.`
    },

    total_deans_list: {
      type: `sum`,
      sql: `deans_list_students`,
      title: `Total Dean's List`,
      description: `Total students achieving Dean's List standing.`
    },

    academic_risk_ratio: {
      type: `number`,
      sql: `${total_on_probation} / NULLIF(${total_semester_headcount}, 0)`,
      title: `Academic Risk Ratio`,
      description: `Ratio of students on academic probation to total enrolled students.`
    },

    total_on_probation: {
      type: `sum`,
      sql: `probation_students`,
      title: `Total Students on Probation`,
      description: `Total students placed on academic probation.`
    },

    courses_per_student: {
      type: `number`,
      sql: `${total_semester_courses} / ${total_semester_headcount}`,
      title: `Courses per Student`,
      description: `Average number of courses taken per enrolled student each semester.`
    },

    total_semester_courses: {
      type: `sum`,
      sql: `unique_courses`,
      title: `Total Semester Courses`,
      description: `Total distinct courses offered across all semesters.`
    },

    total_semester_headcount: {
      type: `sum`,
      sql: `unique_students`,
      title: `Total Semester Headcount`,
      description: `Total distinct students enrolled across all semesters.`
    }
  },
  
  pre_aggregations: {
    enrollment_by_semester_type_quarterly: {
      type: `rollup`,
      measures: [CUBE.total_semester_enrollments, CUBE.total_semester_headcount, CUBE.total_deans_list],
      dimensions: [CUBE.semester_type, CUBE.academic_year],
      time_dimension: CUBE.start_date,
      granularity: `quarter`,
      refresh_key: {
        every: `12 hours`
      }
    }
  }
});
