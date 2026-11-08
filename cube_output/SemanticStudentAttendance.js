cube(`SemanticStudentAttendance`, {
  sql: `SELECT * FROM public.student_attendance`,

  joins: {
    SemanticCoursePerformance: {
      sql: `${SemanticStudentAttendance}.section_id = ${SemanticCoursePerformance}.course_id`,
      relationship: `many_to_one`
    }
  },

  dimensions: {
    student_id: {
      sql: `student_id`,
      type: `string`,
      title: `Student ID`,
      primaryKey: true,
      description: `Unique student identifier`
    },

    course_id: {
      sql: `section_id`,
      type: `string`,
      title: `Course ID`,
      description: `Links each attendance record to its course (joins to SemanticCoursePerformance)`
    },

    school_id: {
      sql: `school_id`,
      type: `string`,
      title: `School ID`,
      description: `Links each attendance record to its school`
    },

    academic_year: {
      sql: `academic_year`,
      type: `string`,
      title: `Academic Year`,
      description: `Academic year (e.g. 2024-2025).`
    },

    semester_name: {
      sql: `semester_name`,
      type: `string`,
      title: `Semester`,
      description: `Semester name (e.g. Fall 2024).`
    },

    semester_type: {
      sql: `semester_type`,
      type: `string`,
      title: `Semester Type`,
      description: `Season: Fall, Spring, or Summer.`
    },

    school_name: {
      sql: `school_name`,
      type: `string`,
      title: `School`,
      description: `Full name of the school.`
    },

    gradespan: {
      sql: `gradespan`,
      type: `string`,
      title: `Gradespan`,
      description: `Grade span of the school (e.g. K-8, 9-12).`
    },

    is_odp_student: {
      sql: `is_odp_student`,
      type: `string`,
      title: `ODP Student`,
      description: `1 if the student is in an out-of-district placement.`
    },

    semester_status: {
      sql: `semester_status`,
      type: `string`,
      title: `Semester Status`,
      description: `Current status: Active, Completed, or Upcoming.`
    },

    semester_start_date: {
      sql: `semester_start_date`,
      type: `time`,
      title: `Semester Start Date`,
      description: `Date the semester began; aggregation time dimension.`
    }
  },

  measures: {
    tardy_days: {
      type: `sum`,
      sql: `case when is_odp_student = 0 then days_tardy else null end`,
      title: `Tardy Days (non-ODP)`,
      description: `Total tardy days for non-ODP students. All reporting should exclude out-of-district placement (ODP) students.
`
    },

    avg_attendance_rate: {
      type: `avg`,
      sql: `attendance_rate`,
      title: `Avg Attendance Rate`,
      description: `Average daily attendance rate (days present / days enrolled), 0–1 scale.`
    },

    total_days_enrolled: {
      type: `sum`,
      sql: `days_enrolled`,
      title: `Total Days Enrolled`,
      description: `Total enrolled school days across all students.`
    },

    absent_days: {
      type: `sum`,
      sql: `days_absent`,
      title: `Absent Days`,
      description: `Total absent days across all students.`
    },

    total_tardy_days: {
      type: `sum`,
      sql: `case when is_odp_student = 0 then days_tardy else null end`,
      title: `Total Tardy Days`,
      description: `Sum of tardy days for non-ODP students.`
    },

    school_attendance_rate: {
      type: `avg`,
      sql: `attendance_rate`,
      title: `School Attendance Rate`,
      description: `Average daily attendance rate across all students.`,
      format: `percent`
    },

    total_absent_days: {
      type: `sum`,
      sql: `days_absent`,
      title: `Total Absent Days`,
      description: `Sum of absent days across all students.`
    },

    total_enrolled_days: {
      type: `sum`,
      sql: `days_enrolled`,
      title: `Total Enrolled Days`,
      description: `Total enrolled school days across all students.`
    },

    chronic_absence_rate: {
      type: `number`,
      sql: `${total_absent_days} / NULLIF(${total_enrolled_days}, 0)`,
      title: `Chronic Absence Rate`,
      description: `Ratio of absent days to enrolled days across all students — a key indicator for chronic absenteeism tracking.
`,
      format: `percent`
    }
  },

  pre_aggregations: {
    attendance_by_school_semester: {
      type: `rollup`,
      measures: [CUBE.total_days_enrolled, CUBE.avg_attendance_rate, CUBE.tardy_days, CUBE.absent_days],
      dimensions: [CUBE.school_name, CUBE.gradespan, CUBE.semester_name, CUBE.academic_year, CUBE.is_odp_student],
      refresh_key: {
        every: `1 day`
      }
    }
  }
});
