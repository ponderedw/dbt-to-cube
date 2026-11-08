cube(`StudentAttendance`, {
  sql: `SELECT * FROM public.student_attendance`,

  dimensions: {
    student_id: {
      sql: `student_id`,
      type: `number`,
      title: `Student ID`,
      description: `Unique student identifier`
    },

    section_id: {
      sql: `section_id`,
      type: `number`,
      title: `Course (Section ID)`,
      description: `Physical course section column (logical name: course_id)`
    },

    school_id: {
      sql: `school_id`,
      type: `string`,
      title: `School ID`,
      description: `Unique school identifier`
    },

    academic_year: {
      sql: `academic_year`,
      type: `string`,
      title: `Academic Year`,
      description: `Academic year (e.g. 2024-2025)`
    },

    semester_name: {
      sql: `semester_name`,
      type: `string`,
      title: `Semester`,
      description: `Semester name (e.g. Fall 2024)`
    },

    semester_type: {
      sql: `semester_type`,
      type: `string`,
      title: `Semester Type`,
      description: `Season of the semester: Fall, Spring, or Summer`
    },

    school_name: {
      sql: `school_name`,
      type: `string`,
      title: `School`,
      description: `Full name of the school`
    },

    gradespan: {
      sql: `gradespan`,
      type: `string`,
      title: `Gradespan`,
      description: `Grade span of the school (e.g. K-8, 9-12)`
    },

    is_odp_student: {
      sql: `is_odp_student`,
      type: `number`,
      title: `ODP Student`,
      description: `1 if the student is in an out-of-district placement (ODP)`
    }
  },

  measures: {
    total_days_enrolled: {
      type: `sum`,
      sql: `days_enrolled`,
      title: `Total Days Enrolled`,
      description: `Total enrolled school days across all students`
    },

    attendance_rate: {
      type: `avg`,
      sql: `attendance_rate`,
      title: `Attendance Rate`,
      description: `Average daily attendance rate (days present / days enrolled)`,
      format: `percent`
    },

    tardy_days: {
      type: `sum`,
      sql: `days_tardy`,
      title: `Tardy Days`,
      description: `Total tardy days for non-ODP students. All reporting should exclude ODP students.
`,
      filters: [{ sql: `is_odp_student = 0` }]
    },

    absence_rate_non_odp: {
      type: `avg`,
      sql: `absence_rate`,
      title: `Absence Rate (non-ODP)`,
      description: `Average absence rate for non-ODP students, as a percentage.
`,
      format: `percent`,
      filters: [{ sql: `is_odp_student = 0` }]
    },

    chronic_absence_days: {
      type: `sum`,
      sql: `days_absent`,
      title: `Chronic Absence Days`,
      description: `Total absent days (complement of attendance)`
    }
  },

  pre_aggregations: {
    attendance_by_school_semester: {
      type: `rollup`,
      measures: [CUBE.total_days_enrolled, CUBE.attendance_rate, CUBE.tardy_days, CUBE.absence_rate_non_odp, CUBE.chronic_absence_days],
      dimensions: [CUBE.school_name, CUBE.gradespan, CUBE.semester_name, CUBE.academic_year, CUBE.is_odp_student],
      refresh_key: {
        every: `1 day`
      }
    }
  }
});
