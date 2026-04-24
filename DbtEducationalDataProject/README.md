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

---

## Why dbt?

dbt is the industry standard for analytics engineering because it brings software-engineering discipline to SQL transformations. Key advantages demonstrated in this project:

### Single Source of Truth for Transformations
Every transformation is a SQL file with an explicit name and location. There are no hidden stored procedures or ad-hoc scripts — all logic lives in version-controlled `.sql` files that any engineer can read, run, and improve.

### Automatic Dependency Graph (DAG)
`{{ ref('model_name') }}` and `{{ source('source', 'table') }}` tell dbt exactly how models depend on each other. dbt builds a full directed acyclic graph (DAG), so it always runs models in the correct order and can parallelize independent branches. You can also visualize the lineage for free via `dbt docs serve`.

```sql
-- dbt resolves this reference at run-time; no hardcoded schema names
SELECT * FROM {{ ref('stg_students') }}
```

### Layered Architecture Enforces Clean Separation of Concerns
The staging → intermediate → marts pattern keeps raw data cleaning separate from business logic and from end-user-facing tables. Downstream consumers (dashboards, APIs) always query stable mart-layer models — never raw sources.

| Layer | Purpose | Example |
|-------|---------|---------|
| Staging | Rename, cast, light cleaning | `stg_students`, `stg_courses` |
| Intermediate | Complex joins, business logic | `int_student_enrollment_history` |
| Marts | Polished, wide tables for analytics | `student_academic_summary` |

### Documentation and Column Descriptions Are First-Class
Every model and column can carry a human-readable description in YAML, and `dbt docs generate` turns those into a searchable documentation site. These descriptions also flow downstream — this project uses them to auto-populate Cube.js titles and Superset column descriptions with no extra work.

```yaml
columns:
  - name: course_id
    description: "Unique identifier for the course"
    tests:
      - unique
      - not_null
```

### Built-in Data Quality Testing
`dbt test` runs schema tests (uniqueness, not-null, referential integrity, accepted values) and any custom SQL assertions you define. Tests are defined in the same YAML files as your documentation, so quality checks stay close to the models they guard.

### Macros Enable Reusable SQL Logic
Jinja macros eliminate copy-paste SQL. Shared calculations like GPA computation and academic-year derivation are defined once and referenced everywhere:

```sql
{{ calculate_gpa(grade_points, credit_hours) }}
{{ academic_year_from_date(semester_start_date) }}
```

### Metadata-Rich Artifacts Power Downstream Automation
`dbt docs generate` produces `manifest.json` and `catalog.json` — structured JSON files that capture every model, column, data type, test, and dependency. Any tool that can read JSON can consume this metadata. This project uses it to drive Cube.js schema generation and BI tool synchronization automatically (see [Using dbt-cube-sync](#using-dbt-cube-sync) below).

---

## Using dbt-cube-sync

[dbt-cube-sync](../dbt-cube-sync/README.md) is the CLI that reads dbt's generated artifacts and automates the rest of the analytics stack — no manual configuration in Cube.js or Superset required.

### How It Works

```
dbt docs generate
      ↓
manifest.json + catalog.json
      ↓
dbt-cube-sync dbt-to-cube   →   Cube.js schema files (.js)
      ↓
dbt-cube-sync cube-to-bi    →   Superset datasets with columns & metrics
```

Models that have a `metrics` block in their `config.meta` are converted to Cube.js cubes. Columns defined in the dbt YAML become Cube.js dimensions; metrics become Cube.js measures and then Superset calculated metrics.

### Defining Metrics in dbt YAML

Add a `meta.metrics` block to any mart model to make it eligible for sync:

```yaml
models:
  - name: course_performance_summary
    config:
      meta:
        metrics:
          average_course_gpa:
            type: avg
            sql: avg_grade_points
            title: "Average Course GPA"
            description: "Average grade points achieved across all enrolled students"
          total_course_enrollments:
            type: sum
            sql: total_enrollments
            title: "Total Course Enrollments"
            description: "Sum of all student enrollments for this course"
```

### Running the Full Pipeline

**Docker (recommended — everything starts automatically):**
```bash
docker-compose up --build
# dbt-cube-sync runs automatically after dbt and Superset are ready
```

**Manual step-by-step:**
```bash
# 1. Generate dbt artifacts
dbt deps && dbt run && dbt docs generate

# 2. Convert dbt models to Cube.js schemas
dbt-cube-sync dbt-to-cube \
  --manifest ./target/manifest.json \
  --catalog ./target/catalog.json \
  --output ../cube_output

# 3. Sync Cube.js schemas to Superset
dbt-cube-sync cube-to-bi superset \
  --cube-files ../cube_output \
  --url http://localhost:8088 \
  --username admin \
  --password admin \
  --cube-connection-name Cube
```

**Incremental sync (only re-process changed models):**
```bash
dbt-cube-sync sync-all \
  --manifest ./target/manifest.json \
  --catalog ./target/catalog.json \
  --output ../cube_output \
  --superset-url http://localhost:8088 \
  --superset-username admin \
  --superset-password admin
```

### What Gets Created in Superset

For each eligible dbt model, dbt-cube-sync automatically creates or updates a Superset dataset with:
- **Columns** — one per dbt column, with the dbt description as the Superset column description
- **Metrics** — one per `meta.metrics` entry, using `MEASURE(CubeName.metric_name)` syntax so Cube.js handles aggregation
- **Verbose names** — derived from the column/metric name, always human-readable

---

## Why This Approach?

The dbt → Cube.js → Superset pipeline solves the most common analytics engineering pain point: keeping metric definitions consistent across data transformation, semantic layer, and BI tool.

### One Definition, Everywhere
With traditional setups, `average_gpa` might be calculated differently in dbt models, as a Superset custom metric, and in a Tableau calculated field — subtle divergences that erode trust in numbers. With this pipeline, the definition lives once in dbt YAML and flows automatically to every downstream system.

### Descriptions Follow the Data
Column and metric descriptions written in dbt YAML appear in Superset without any manual copy-paste. When a description changes in dbt, rerunning the pipeline updates Superset too.

### Cube.js as a Consistent Semantic Layer
All BI tools query through Cube.js rather than PostgreSQL directly. This means:
- Aggregation logic runs in one place (Cube.js measures)
- Pre-aggregations cache heavy queries automatically
- Adding a new BI tool (Tableau, PowerBI) requires zero changes to dbt or Cube.js

### Incremental Sync Keeps It Fast
The state file (`.dbt-cube-sync-state.json`) tracks model checksums. Only models whose dbt YAML or SQL changed since the last run are regenerated and re-synced. A full project rebuild is a one-time cost; ongoing runs are fast regardless of how many models the project contains.

### No Manual BI Configuration
New mart models with a `metrics` block in their YAML go from dbt YAML → Cube.js schema → Superset dataset fully automatically, including correct column types, descriptions, and calculated metrics. Analysts spend time writing SQL, not clicking through BI tool setup screens.