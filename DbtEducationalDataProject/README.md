# DbtEducationalDataProject

A comprehensive educational data analytics project built with dbt, featuring 45 interconnected models that analyze student performance, faculty effectiveness, financial metrics, and institutional operations.

## Project Overview

This project models a complete educational institution's data ecosystem, including:

### Data Sources
- **Students**: Enrollment, demographics, academic standing
- **Faculty**: Employment, teaching assignments, compensation
- **Courses**: Catalog, prerequisites, difficulty levels
- **Departments**: Budgets, organization structure
- **Enrollments**: Course registrations and performance
- **Assignments**: Coursework and submission tracking
- **Financial**: Tuition payments and financial aid
- **Academic Calendar**: Semesters and schedules

### Model Architecture

#### Staging Layer (12 models)
Data cleaning and standardization:
- `stg_students`, `stg_faculty`, `stg_courses`, `stg_departments`
- `stg_enrollments`, `stg_semesters`, `stg_class_sessions`
- `stg_assignments`, `stg_assignment_submissions`
- `stg_financial_aid`, `stg_tuition_payments`

#### Intermediate Layer (12 models)
Complex business logic and relationships:
- `int_student_enrollment_history`: Student academic progression
- `int_course_performance_metrics`: Course success analytics
- `int_faculty_teaching_load`: Teaching workload analysis
- `int_department_analytics`: Departmental performance
- `int_assignment_performance`: Assignment effectiveness
- `int_student_at_risk_indicators`: Early warning system
- `int_course_prerequisite_chains`: Curriculum sequencing
- `int_grade_inflation_analysis`: Grading trends
- `int_faculty_student_interactions`: Teaching effectiveness
- `int_academic_collaboration_networks`: Student connections
- `int_student_success_predictors`: Retention modeling
- `int_resource_utilization_analysis`: Operational efficiency
- `int_curriculum_flow_analysis`: Learning pathway optimization

#### Marts Layer (21 models)

**Core Business Models (9):**
- `student_academic_summary`: Comprehensive student profiles
- `course_catalog_enhanced`: Enhanced course information
- `faculty_performance_dashboard`: Teaching effectiveness metrics
- `department_efficiency_report`: Operational performance
- `graduation_pathway_analysis`: Degree completion tracking
- `institutional_effectiveness_dashboard`: Executive metrics
- `academic_early_warning_system`: Student intervention alerts
- `institutional_kpi_dashboard`: Key performance indicators

**Academic Analytics (7):**
- `student_retention_analysis`: Dropout prevention
- `course_success_predictors`: Academic outcome modeling
- `semester_enrollment_trends`: Enrollment patterns
- `instructor_effectiveness_scorecard`: Teaching quality
- `assignment_workload_analysis`: Course load optimization
- `learning_outcome_assessment`: Educational effectiveness
- `course_difficulty_calibration`: Curriculum standards
- `competitive_program_benchmarking`: Program comparison

**Financial Analytics (5):**
- `student_financial_profile`: Individual financial tracking
- `tuition_revenue_analysis`: Revenue management
- `financial_aid_impact_analysis`: Aid effectiveness
- `institutional_revenue_optimization`: Financial planning
- `budget_allocation_optimization`: Resource allocation

### Key Features

#### Complex Dependencies
- Models reference multiple upstream sources
- Layered transformations with intermediate calculations
- Cross-functional analysis spanning academic and financial domains

#### Advanced Analytics
- Predictive modeling for student success
- Network analysis for student collaboration
- Time-series analysis for trends
- Risk scoring and early warning systems

#### Business Intelligence
- Executive dashboards and KPI tracking
- Comparative benchmarking
- Resource optimization recommendations
- Financial performance analysis

### Macros and Utilities
- `grade_point_calculator`: Grade to GPA conversion
- `academic_year_from_date`: Academic year calculation
- `calculate_gpa`: Weighted GPA computation
- `test_referential_integrity`: Data quality testing

### Seeds and Reference Data
- `grade_scale_reference`: Grading standards
- `semester_calendar`: Academic calendar
- `academic_calendar_holidays`: Holiday tracking

## Getting Started

### Local Development

1. **Setup Profiles**:
   ```bash
   cp profiles.yml ~/.dbt/profiles.yml
   ```

2. **Install Dependencies**:
   ```bash
   dbt deps
   ```

3. **Run Models**:
   ```bash
   dbt run
   ```

4. **Test Data Quality**:
   ```bash
   dbt test
   ```

5. **Generate Documentation**:
   ```bash
   dbt docs generate
   dbt docs serve
   ```

### Docker Setup

For a containerized environment with dbt docs:

1. **Start the Educational dbt Docs Server**:
   ```bash
   just educational-dbt-docs
   ```

2. **Access the Documentation**:
   Open your browser to [http://localhost:8502](http://localhost:8502)

3. **Stop the Server**:
   ```bash
   just educational-dbt-docs-down
   ```

The Docker setup includes:
- Uses existing PostgreSQL database from main docker-compose
- dbt docs server (port 8502)
- Automatic model compilation and documentation generation
- All dependencies and setup handled automatically

**Note**: Make sure the main postgres service is running first:
```bash
docker compose -f docker-compose.postgres.yml up -d
```

## Model Dependencies

The project follows a strict dependency hierarchy:
- Staging → Intermediate → Marts
- Complex cross-model references in intermediate layer
- Business-ready outputs in marts layer

## Use Cases

### Academic Leadership
- Monitor student retention and success rates
- Evaluate faculty teaching effectiveness
- Optimize course offerings and scheduling
- Track graduation pathways and bottlenecks

### Financial Management
- Analyze tuition revenue and collection
- Optimize financial aid allocation
- Monitor departmental budget performance
- Forecast enrollment and revenue

### Student Services
- Early identification of at-risk students
- Academic planning and course sequencing
- Financial counseling and aid optimization
- Collaborative learning network analysis

### Institutional Research
- Comparative program benchmarking
- Curriculum effectiveness assessment
- Resource utilization optimization
- Strategic planning and forecasting

## Data Quality

The project includes comprehensive data quality tests:
- Referential integrity checks
- Business rule validation
- Data freshness monitoring
- Anomaly detection

## Technology Stack

- **dbt**: Data transformation and modeling
- **PostgreSQL**: Data warehouse
- **SQL**: Core transformation logic
- **Jinja**: Templating and macros