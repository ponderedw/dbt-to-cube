# dbt-cube-sync: Modern Data Stack Pipeline

🚀 **Automated pipeline for converting dbt models to Cube.js schemas and syncing to BI tools**

A complete data stack solution that transforms dbt models into Cube.js semantic layers and automatically syncs them to Business Intelligence tools like Superset, Tableau, and PowerBI.

## 🎯 Features

- **🔄 dbt → Cube.js**: Convert dbt models to Cube.js schemas with dimensions and measures
- **📊 BI Integration**: Sync Cube.js schemas to Superset, Tableau, PowerBI
- **🐳 Docker Orchestration**: Complete containerized setup with dependency management
- **⚙️ CLI Tools**: Easy-to-use command-line interface for manual and automated workflows
- **🔌 Extensible**: Plugin architecture for adding new BI tools
- **📈 Production Ready**: Automated metrics creation, column metadata, and error handling
- **🧠 MetricFlow Semantic Layer**: Full support for dbt MetricFlow (v1 and v2 Fusion format)
- **🔗 Cube.js Joins**: Auto-generated from dbt foreign-key entities
- **🏷️ Labels & Titles**: `label:` on metrics and dimensions flows to Cube.js `title:`
- **🎨 Number Formatting**: `config.meta.format: "percent"` → Cube.js `format: 'percent'`
- **🔍 Metric Filters**: `config.meta.filter: "${CUBE}.col = val"` → Cube.js `filters: [...]`

## 🏗️ Architecture

```
dbt Models → manifest.json/catalog.json → Cube.js Schemas → BI Tools (Superset/Tableau/PowerBI)
     ↓              ↓                         ↓                    ↓
PostgreSQL → dbt transformations → Semantic Layer → Dashboards & Analytics
```

## 📋 Prerequisites

- Docker & Docker Compose
- Git

## 🚀 Quick Start

### 1. Clone & Start

```bash
git clone <repository-url>
cd dbt-to-cube
docker-compose up --build
```

### 2. Access Services

- **📊 Superset**: http://localhost:8088 (admin/admin)
- **📚 dbt Docs**: http://localhost:8080
- **🔌 Cube.js API**: http://localhost:4000
- **🗄️ PostgreSQL**: localhost:5432

### 3. Pipeline Execution

The pipeline runs automatically on startup! Watch the logs:

```bash
docker-compose logs -f dbt-cube-sync
```

## 🛠️ CLI Usage

### Two Main Commands

#### 1. dbt-to-cube: Convert dbt models to Cube.js

```bash
dbt-cube-sync dbt-to-cube \
  --manifest /path/to/manifest.json \
  --catalog /path/to/catalog.json \
  --output /path/to/cube/output
```

**Parameters:**
- `--manifest, -m`: Path to dbt manifest.json file (required)
- `--catalog, -c`: Path to dbt catalog.json file (required)  
- `--output, -o`: Output directory for Cube.js files (required)
- `--template-dir, -t`: Directory containing Cube.js templates (optional)

#### 2. cube-to-bi: Sync Cube.js to BI tools

```bash
dbt-cube-sync cube-to-bi superset \
  --cube-files /path/to/cube/files \
  --url http://localhost:8088 \
  --username admin \
  --password admin \
  --cube-connection-name Cube
```

**Parameters:**
- `bi_tool`: BI tool type (superset|tableau|powerbi)
- `--cube-files, -c`: Directory containing Cube.js files (required)
- `--url, -u`: BI tool URL (required)
- `--username, -n`: Username (required)
- `--password, -p`: Password (required)
- `--cube-connection-name, -d`: Database connection name (default: "Cube")

### Manual Execution Examples

```bash
# Run inside the dbt-cube-sync container
docker-compose exec dbt-cube-sync dbt-cube-sync --help

# Generate Cube.js schemas
docker-compose exec dbt-cube-sync dbt-cube-sync dbt-to-cube \
  -m /workspace/DbtEducationalDataProject/target/manifest.json \
  -c /workspace/DbtEducationalDataProject/target/catalog.json \
  -o /workspace/cube_output

# Sync to Superset
docker-compose exec dbt-cube-sync dbt-cube-sync cube-to-bi superset \
  -c /workspace/cube_output \
  -u http://superset:8088 \
  -n admin \
  -p admin \
  -d Cube
```

## 🧠 MetricFlow Semantic Layer

> **Use Format 3 (inline).** It is the preferred format for all new semantic layer
> work at Ponder, works with both dbt 1.x and dbt-fusion 2.x, and is the only format
> that supports `dbt_simple_metrics` macros under dbt-fusion 2.x. For the full format
> reference see [`SEMANTIC_LAYER_FORMATS.md`](SEMANTIC_LAYER_FORMATS.md).

Three metric input formats are supported:

### Format 1: `config.meta.metrics` (Ponder custom)
Works with every dbt version. Metrics are plain dicts inside `config.meta.metrics` on
the model. Used for backward compatibility and when MetricFlow is unavailable.

### Format 2: MetricFlow v1 (top-level `semantic_models:` + `metrics:`) — legacy
Used by dbt 1.5–1.11. Semantic models and metrics live in separate top-level YAML keys.
**Do not use for new models** — incompatible with dbt-fusion 2.x macros.

```yaml
# models/semantic_models.yml
semantic_models:
  - name: orders
    model: ref('orders')
    entities:
      - name: order_id
        type: primary
    dimensions:
      - name: country
        type: categorical
    measures:
      - name: order_count
        agg: count
        expr: order_id
        agg_time_dimension: order_date

metrics:
  - name: total_orders
    type: simple
    type_params:
      measure: order_count
```

### Format 3: MetricFlow v2 inline ✓ PREFERRED (dbt 1.9+, dbt-fusion 2.x)
Semantic model, entities, dimensions, and metrics all live inside the model definition.
Requires `dbt_simple_metrics` v1.0.9+ for dbt-fusion 2.x compatibility.

```yaml
# models/orders/schema.yml
models:
  - name: orders
    semantic_model:
      enabled: true
    agg_time_dimension: order_date

    columns:
      - name: order_id
        entity:
          type: primary
          name: order
      - name: order_date
        granularity: day
        dimension:
          type: time
      - name: country
        dimension:
          type: categorical

    metrics:
      - name: total_orders
        label: "Total Orders"
        description: "Count of all orders"
        type: simple
        agg: count
        expr: 1

      # Metric-level filter — MetricFlow native syntax (supported by dbt_simple_metrics v1.0.9+)
      - name: us_orders
        label: "US Orders"
        type: simple
        agg: count
        expr: 1
        filter: "{{ Dimension('order__country') }} = 'US'"
        # compiles to: count(case when country = 'US' then 1 end)

# Top-level advanced metrics (ratio, derived, cumulative)
# Note: no type_params wrapper in v2 format
metrics:
  - name: return_rate
    label: "Return Rate"
    type: ratio
    numerator: returned_orders
    denominator: total_orders
    config:
      meta:
        format: "percent"

  - name: revenue_per_customer
    label: "Revenue per Customer"
    type: derived
    expr: total_revenue / unique_customers
    input_metrics:
      - name: total_revenue
      - name: unique_customers

  - name: cumulative_revenue
    label: "Cumulative Revenue"
    type: cumulative
    input_metric: total_revenue
```

### Semantic Layer Features

| Feature | dbt YAML | Cube.js output |
|---|---|---|
| Human-readable title | `label: "Total Orders"` | `title: 'Total Orders'` |
| Number format | `config.meta.format: "percent"` | `format: 'percent'` |
| Metric filter | `config.meta.filter: "${CUBE}.col = val"` | `filters: [{ sql: ... }]` |
| Measure filter | CASE WHEN in `expr:` | SQL in `sql:` field |
| Cube.js joins | `entity: { type: foreign }` matching another SM's primary entity | `joins: { TargetCube: { sql, relationship } }` |
| Pre-aggregations | `config.meta.pre_aggregations:` on the model | `pre_aggregations: { ... }` |

### Filter Patterns

**Measure-level filtering** (ODP student exclusion example from production):
```yaml
# In the metric expr — CASE WHEN is the safest pattern
- name: present_days
  type: simple
  agg: sum
  expr: >
    case when current_odp = 0 then 1 else 0 end
```

**Metric-level filtering — MetricFlow native syntax** (Format 3, `dbt_simple_metrics` v1.0.9+):
```yaml
- name: active_students
  type: simple
  agg: count_distinct
  expr: student_id
  filter: "{{ Dimension('student__is_active') }} = 1"
  # compiles to: count(distinct case when is_active = 1 then student_id end)
```

**Metric-level filtering — Cube.js-style** (Format 1 `config.meta.filter`, or when MetricFlow DSL isn't available):
```yaml
- name: active_students
  config:
    meta:
      filter: "${CUBE}.is_active = 1"
```

### Format Values

| `config.meta.format` | Cube.js `format` |
|---|---|
| `"percent"` or any string containing `%` | `'percent'` |
| `"currency"` or strings starting with `$` | `'currency'` |
| Any other string (e.g. `"0.00"`) | passed through as-is |

### Joins from Foreign Entities

Cube.js joins are auto-generated when a semantic model has a `foreign` entity whose name matches a `primary` entity in another semantic model:

```yaml
# semantic_model A (attendance)
entities:
  - name: course_id       # ← matches the primary entity name in model B
    type: foreign
    expr: section_id      # physical column name

# semantic_model B (courses)
entities:
  - name: course_id
    type: primary
    expr: course_id
```

Generates in Cube.js:
```javascript
joins: {
  Courses: {
    sql: `${Attendance}.section_id = ${Courses}.course_id`,
    relationship: `many_to_one`
  }
}
```

## 📁 Project Structure

```
dbt-to-cube/
├── dbt-cube-sync/                 # Python CLI package
│   ├── dbt_cube_sync/
│   │   ├── cli.py                # CLI interface
│   │   ├── core/                 # Core parsing & generation
│   │   ├── connectors/           # BI tool connectors
│   │   └── config.py             # Configuration management
│   ├── pyproject.toml            # Poetry dependencies
│   └── Dockerfile                # Container definition
├── DbtEducationalDataProject/    # dbt project
│   ├── models/                   # dbt models
│   ├── seeds/                    # Sample data
│   └── target/                   # Generated manifest/catalog
├── cube/                         # Cube.js configuration
├── superset-setup/              # Automated Superset setup
├── init/                        # Database initialization
├── docker-compose.yml          # Service orchestration
└── README.md                   # This file
```

## 🔧 Services

### Core Services

| Service | Description | Port | Health Check |
|---------|-------------|------|--------------|
| **postgres** | PostgreSQL database | 5432 | `pg_isready` |
| **dbt** | dbt build & transformations | - | Completion status |
| **dbt-docs** | dbt documentation server | 8080 | HTTP ready |
| **cube_api** | Cube.js semantic layer API | 4000, 15432 | Service started |
| **superset** | Apache Superset BI platform | 8088 | Health endpoint |

### Automation Services

| Service | Description | Dependencies |
|---------|-------------|--------------|
| **dbt-cube-sync** | CLI pipeline automation | dbt, cube_api, superset |
| **superset-setup** | Auto-create database connections | superset, postgres |

## 🎛️ Configuration

### Environment Variables

Create `.env` file for Cube.js configuration:

```env
CUBEJS_DEV_MODE=true
CUBEJS_DB_TYPE=postgres
CUBEJS_DB_HOST=postgres
CUBEJS_DB_NAME=education_dw
CUBEJS_DB_USER=dbt_user
CUBEJS_DB_PASS=dbt_password
CUBEJS_API_SECRET=your-secret-key
```

### Superset Configuration

Superset is automatically configured with:
- Admin user: `admin/admin`
- Database connection: "Cube" pointing to PostgreSQL
- Custom configuration in `superset_config.py`

## 📊 Data Pipeline

### Sample Data

The project includes educational data with:
- **Students**: 8 student records
- **Courses**: 12 courses across 5 departments  
- **Enrollments**: Course registrations and grades
- **Faculty**: Instructor information
- **Financial Aid**: Student financial data

### Generated Assets

**dbt Models (46 total)**:
- Staging models (`stg_*`)
- Intermediate models (`int_*`) 
- Mart models (analytics tables)

**Cube.js Schemas**:
- Dimensions: Course details, student info, time periods
- Measures: GPAs, pass rates, enrollment counts, engagement scores

**Superset Datasets**:
- Auto-created with proper column metadata
- Custom metrics for analysis
- Ready for dashboard building

## 🚧 Development

### Adding New BI Connectors

1. Create connector class inheriting from `BaseConnector`
2. Implement required methods:
   - `_validate_config()`
   - `connect()`
   - `sync_cube_schemas()`
   - `sync_single_schema()`

```python
# Example: connectors/newbi.py
class NewBIConnector(BaseConnector):
    def __init__(self, **config):
        super().__init__(**config)
        # Initialize connector
        
    def sync_cube_schemas(self, cube_dir: str) -> List[SyncResult]:
        # Implementation
        pass

# Register connector
ConnectorRegistry.register('newbi', NewBIConnector)
```

### Testing

```bash
# Run tests inside container
docker-compose exec dbt-cube-sync pytest

# Manual CLI testing
docker-compose exec dbt-cube-sync dbt-cube-sync --version
```

## 🐛 Troubleshooting

### Common Issues

**1. Container Dependencies**
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs <service-name>
```

**2. Database Connection**
```bash
# Test PostgreSQL connection
docker-compose exec postgres psql -U dbt_user -d education_dw -c "\dt"
```

**3. dbt Build Failures**
```bash
# Check dbt logs
docker-compose logs dbt

# Manual dbt run
docker-compose exec dbt dbt run --project-dir /dbt/DbtEducationalDataProject
```

**4. Superset Access**
```bash
# Reset Superset admin
docker-compose exec superset superset fab create-admin \
  --username admin --firstname Admin --lastname Admin \
  --email admin@admin.com --password admin
```

### Pipeline Debugging

Enable verbose logging by modifying the CLI commands in `docker-compose.yml`:

```yaml
# Add debugging flags
dbt-cube-sync dbt-to-cube --verbose \
  --manifest /workspace/DbtEducationalDataProject/target/manifest.json \
  --catalog /workspace/DbtEducationalDataProject/target/catalog.json \
  --output /workspace/cube_output
```

## 📈 Production Deployment

### Scaling Considerations

1. **Database**: Use managed PostgreSQL (AWS RDS, Google Cloud SQL)
2. **dbt**: Schedule with dbt Cloud or Airflow
3. **Cube.js**: Deploy with Redis caching and clustering
4. **Superset**: Use external metadata database and Redis
5. **CLI**: Run as scheduled jobs (GitHub Actions, Jenkins)

### Security

- Use environment variables for credentials
- Enable HTTPS for all services
- Restrict network access with firewalls
- Use secrets management (AWS Secrets Manager, etc.)

### Monitoring

Add monitoring with:
- Prometheus metrics
- Grafana dashboards  
- ELK stack for logging
- Health check endpoints

## 💡 Why dbt?

dbt is the industry standard for analytics engineering because it brings software-engineering discipline to SQL transformations. This project is built on top of dbt's metadata ecosystem — understanding dbt's strengths explains why the whole pipeline works.

### SQL as Code, in Version Control
Every transformation is a `.sql` file with an explicit name. No hidden stored procedures, no ad-hoc scripts — all logic is readable, diffable, and reviewable in Git.

### Automatic Dependency Graph (DAG)
`{{ ref('model_name') }}` and `{{ source('source', 'table') }}` declare dependencies explicitly. dbt builds a full DAG and always runs models in the correct order, parallelizing independent branches automatically. Lineage is visible for free via `dbt docs serve`.

```sql
-- dbt resolves the schema at run-time; no hardcoded database names
SELECT * FROM {{ ref('stg_students') }}
```

### Layered Architecture
The staging → intermediate → marts pattern keeps raw-data cleaning separate from business logic and from end-user-facing tables. BI tools always query stable mart-layer models — never raw sources.

| Layer | Purpose |
|-------|---------|
| Staging | Rename, cast, light cleaning |
| Intermediate | Complex joins, business logic |
| Marts | Wide, polished tables for analytics |

### Column Descriptions Are First-Class
Descriptions in dbt YAML are not just documentation — this pipeline reads them directly and writes them to Cube.js `title`/`description` fields and Superset column descriptions automatically.

```yaml
columns:
  - name: course_id
    description: "Unique identifier for the course"
    tests:
      - unique
      - not_null
```

### Built-in Data Quality Tests
`dbt test` runs schema tests (uniqueness, not-null, referential integrity, accepted values) defined alongside the same YAML that documents the columns. Tests and docs stay in sync.

### Metadata-Rich Artifacts Drive Automation
`dbt docs generate` produces `manifest.json` and `catalog.json` — structured JSON capturing every model, column, data type, test, and dependency. dbt-cube-sync reads these files to generate Cube.js schemas and configure Superset with zero manual steps.

---

## 🚀 Why This Approach?

The dbt → Cube.js → Superset pipeline solves the most common analytics engineering pain point: metric definitions diverging between the transformation layer, the semantic layer, and the BI tool.

### One Definition, Everywhere
`average_gpa` is calculated once — in dbt YAML — and flows automatically to Cube.js and Superset. No risk of subtle divergence between dashboard metrics and warehouse logic.

### Descriptions Travel With the Data
Column and metric descriptions written in dbt YAML appear in Superset without any copy-paste. Updating a description in dbt and rerunning the pipeline updates Superset too.

### Cube.js as a Consistent Semantic Layer
All BI tools query through Cube.js rather than PostgreSQL directly:
- Aggregation logic runs in one place (Cube.js measures)
- Pre-aggregations cache heavy queries automatically
- Adding a new BI tool requires zero changes to dbt or Cube.js schemas

### Incremental Sync Keeps It Fast
The state file (`.dbt-cube-sync-state.json`) tracks model checksums. Only models whose YAML or SQL changed since the last run are regenerated and re-synced — a full project rebuild is a one-time cost.

### No Manual BI Configuration
New mart models with a `metrics` block in their dbt YAML go from definition → Cube.js schema → Superset dataset fully automatically, with correct column types, descriptions, and calculated metrics.

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **dbt**: For the amazing data transformation framework
- **Cube.js**: For the powerful semantic layer API
- **Apache Superset**: For the open-source BI platform
- **PostgreSQL**: For the robust database foundation

---

**🎉 Happy Analyzing!** Build amazing dashboards with your automated data pipeline!