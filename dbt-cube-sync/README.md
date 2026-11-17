# dbt-cube-sync

A powerful synchronization tool that creates a seamless pipeline from dbt models to Cube.js schemas and BI tools (Superset, Tableau, PowerBI).

## Features

- 🔄 **dbt → Cube.js**: Auto-generate Cube.js schemas from dbt models with metrics
- 📐 **All metric formats**: Reads `config.meta.metrics` (Format 1), MetricFlow v1 standalone (Format 2), and MetricFlow v2 inline (Format 3) from the dbt manifest
- 🗃️ **Flexible Data Type Source**: Get column types from catalog OR directly from database via SQLAlchemy
- 🎯 **Model Filtering**: Process specific models instead of all models
- 📊 **Cube.js → BI Tools**: Sync schemas to multiple BI platforms
- 🏗️ **Extensible Architecture**: Plugin-based connector system for easy BI tool integration
- 🐳 **Docker Support**: Containerized execution with orchestration support
- 🎯 **CLI Interface**: Simple command-line tools for automation

## Metric format support

`dbt-cube-sync` reads from `manifest.json` directly in Python and is not affected by
dbt version differences in the Jinja context. All three formats work:

| Format | Parser | dbt versions |
|--------|--------|-------------|
| `config.meta.metrics` | `DbtParser` | Any |
| MetricFlow v1 standalone (`semantic_models:` + `metrics:` YAML) | `MetricFlowParser` | 1.5–1.11 |
| MetricFlow v2 inline (metrics nested under model) | `MetricFlowParser` | dbt 1.9+, dbt-fusion 2.x |

For the full format reference see [`SEMANTIC_LAYER_FORMATS.md`](../SEMANTIC_LAYER_FORMATS.md).

## Supported BI Tools

- ✅ **Apache Superset** - Full implementation
- 🚧 **Tableau** - Placeholder (coming soon)
- 🚧 **PowerBI** - Placeholder (coming soon)

## Supported MetricFlow Aggregation Types

| MetricFlow `agg` | Cube.js type | SQL generated |
|---|---|---|
| `sum` | `sum` | column expression |
| `avg` / `average` | `avg` | column expression |
| `count` | `count` | column expression |
| `count_distinct` | `countDistinct` | column expression |
| `count_distinct_approx` | `countDistinctApprox` | column expression |
| `min` / `max` | `min` / `max` | column expression |
| `median` | `number` | `MEDIAN(col)` |
| `sum_boolean` | `sum` | `CASE WHEN col THEN 1 ELSE 0 END` |
| `percentile` | `number` | `PERCENTILE_CONT/DISC(val) WITHIN GROUP (ORDER BY col)` — reads `agg_params.percentile` and `use_discrete_percentile` |

**Conversion metrics** (`type: conversion`) are mapped to a `number` ratio:
`${conversion_measure} / NULLIF(${base_measure}, 0)` with `format: 'percent'`.

## Installation

### Using Poetry (Development)

```bash
cd dbt-cube-sync
poetry install
poetry run dbt-cube-sync --help
```

### Database Drivers (for SQLAlchemy URI feature)

If you want to use the `--sqlalchemy-uri` option to fetch column types directly from your database, you'll need to install the appropriate database driver:

```bash
# PostgreSQL
poetry add psycopg2-binary

# MySQL
poetry add pymysql

# Snowflake
poetry add snowflake-sqlalchemy

# BigQuery
poetry add sqlalchemy-bigquery

# Redshift
poetry add sqlalchemy-redshift
```

### Using Docker

```bash
docker build -t dbt-cube-sync .
docker run --rm dbt-cube-sync --help
```

## Quick Start

### 1. Generate Cube.js Schemas from dbt

**Option A: Using catalog file (traditional method)**
```bash
dbt-cube-sync dbt-to-cube \
  --manifest ./target/manifest.json \
  --catalog ./target/catalog.json \
  --output ./cube_output
```

**Option B: Using database connection (no catalog needed)**
```bash
dbt-cube-sync dbt-to-cube \
  --manifest ./target/manifest.json \
  --sqlalchemy-uri postgresql://user:password@localhost:5432/mydb \
  --output ./cube_output
```

**Option C: Filter specific models**
```bash
dbt-cube-sync dbt-to-cube \
  --manifest ./target/manifest.json \
  --sqlalchemy-uri postgresql://user:password@localhost:5432/mydb \
  --models orders,customers,products \
  --output ./cube_output
```

### 2. Sync to BI Tool (Optional)

```bash
# Sync to Superset
dbt-cube-sync cube-to-bi superset \
  --cube-files ./cube_output \
  --url http://localhost:8088 \
  --username admin \
  --password admin \
  --cube-connection-name Cube
```

## Configuration

### Sample Configuration (`sync-config.yaml`)

```yaml
connectors:
  superset:
    type: superset
    url: http://localhost:8088
    username: admin
    password: admin
    database_name: Cube
    
  tableau:
    type: tableau
    url: https://your-tableau-server.com
    username: your-username
    password: your-password
    
  powerbi:
    type: powerbi
    # PowerBI specific configuration
```

## CLI Commands

### Quick Reference

| Command | Description |
|---------|-------------|
| `sync-all` | **Ultimate command** - Incremental sync: dbt → Cube.js → Superset → RAG |
| `dbt-to-cube` | Generate Cube.js schemas from dbt models (with incremental support) |
| `cube-to-bi` | Sync Cube.js schemas to BI tools (Superset, Tableau, PowerBI) |
| `validate-cubes` | Pre-merge CI validation: generate cubes + test via real Cube.js instance |
| `compare-state` | Compare local manifest checksums against production state |
| `align-ci-manifest` | Align CI manifest with dbt Cloud artifacts |

---

### `sync-all` (Recommended)

**Ultimate incremental sync command** - handles the complete pipeline with state tracking.

```bash
# Basic incremental sync (Cube.js only)
dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output

# Full pipeline: dbt → Cube.js → Superset
dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output \
  --superset-url http://localhost:8088 \
  --superset-username admin \
  --superset-password admin

# Full pipeline: dbt → Cube.js → Superset → RAG embeddings
dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output \
  --superset-url http://localhost:8088 \
  --superset-username admin \
  --superset-password admin \
  --rag-api-url http://localhost:8000

# Force full rebuild (ignore state)
dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output --force-full-sync
```

**Options:**
| Option | Required | Description |
|--------|----------|-------------|
| `--manifest, -m` | Yes | Path to dbt manifest.json |
| `--catalog, -c` | No* | Path to dbt catalog.json |
| `--sqlalchemy-uri, -s` | No* | Database URI for column types |
| `--output, -o` | Yes | Output directory for Cube.js files |
| `--state-path` | No | State file path (default: `.dbt-cube-sync-state.json`) |
| `--force-full-sync` | No | Force full rebuild, ignore state |
| `--superset-url` | No | Superset URL |
| `--superset-username` | No | Superset username |
| `--superset-password` | No | Superset password |
| `--cube-connection-name` | No | Cube database name in Superset (default: `Cube`) |
| `--rag-api-url` | No | RAG API URL for embedding updates |
| `--s3-bucket` | No | S3 bucket to push cube files after generation. Env: `CUBEJS_SCHEMA_S3_BUCKET` |
| `--s3-prefix` | No | S3 key prefix (default: `cubes`). Env: `CUBEJS_SCHEMA_S3_PREFIX` |

*Either `--catalog` or `--sqlalchemy-uri` is required.

> **S3 schema push**: when `--s3-bucket` is set, `sync-all` uploads all generated `.js` files and a `.schema-version` timestamp to S3. The dwe_cube `cube.js` reads schemas directly from S3 when `CUBEJS_SCHEMA_S3_BUCKET` is configured — no SSH to the server needed to push schema updates. Requires `boto3` (`pip install boto3`).

**How Incremental Sync Works:**
1. Reads state file (`.dbt-cube-sync-state.json`) with model checksums
2. Compares against current manifest to detect changes
3. Only processes **added** or **modified** models
4. Deletes Cube.js files for **removed** models
5. Updates state file with new checksums

---

---

### `validate-cubes` (CI validation)

Validates generated Cube.js schemas by spinning up a real Cube.js Docker instance and running test queries against each cube. Designed for use in CI pre-merge checks.

Automatically handles:
- **Incremental mode** via `--state-path`: only validates models that changed
- **Dev schema override** via `--dev-schema`: when dbt Cloud built models in a dev target that differs from the manifest schema

```bash
# Full validation (all models):
dbt-cube-sync validate-cubes \
  -m manifest.json \
  -s "redshift+psycopg2://user:pass@host:5439/db" \
  -o /tmp/cube_test

# CI incremental + dev schema (changed models only):
dbt-cube-sync validate-cubes \
  -m /tmp/manifest.json \
  -s "redshift+psycopg2://$DB_USER:$DB_PASS@$DB_HOST:5439/$DB_NAME" \
  --state-path /tmp/prod_state.json \
  --dev-schema "$CUBE_DEV_SCHEMA" \
  -o /tmp/cube_test \
  --ci-mode
```

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--manifest, -m` | — | dbt manifest.json path |
| `--sqlalchemy-uri, -s` | — | DB URI (auto-parsed for Cube.js config) |
| `--catalog, -c` | — | dbt catalog.json (alternative to URI) |
| `--state-path` | — | Production state file (enables incremental mode) |
| `--output, -o` | — | Output dir for temp cube files |
| `--dev-schema` | — | Schema override for changed/new models. Env: `CUBE_DEV_SCHEMA` |
| `--ci-mode` | `false` | Skip output-file existence checks (CI default) |
| `--cube-image` | `cubejs/cube:latest` | Cube.js Docker image |
| `--port` | `4100` | Local port for Cube.js |
| `--timeout` | `180` | Seconds to wait for Cube.js ready |
| `--db-type` | — | Env: `CUBEJS_DB_TYPE` |
| `--db-host/name/user/pass/port` | — | Env: `CUBEJS_DB_*` |

**Output example:**
```
══════════════════════════════════════════════════════════════
CUBE VALIDATION RESULTS
══════════════════════════════════════════════════════════════

  ✓ Orders                                   PASSED  (1 measure(s) tested, 5 dim(s))
  ✓ Customers                                PASSED  (1 measure(s) tested, 4 dim(s))
  ✗ Products                                 FAILED
  ✗ Revenue                                  FAILED

──────────────────────────────────────────────────────────────
FAILURES (2)
──────────────────────────────────────────────────────────────

  Cube:   Products
  Query:  {"measures": ["Products.total_revenue"], "limit": 1}
  Error:  Error: table "analytics.products" doesn't exist

  Cube:   Revenue
  Query:  {"measures": ["Revenue.total"], "limit": 1}
  Error:  SQL execution failed: column "amount" does not exist

══════════════════════════════════════════════════════════════
RESULT: 2/4 passed, 2 FAILED
══════════════════════════════════════════════════════════════
```

---

### `dbt-to-cube`

Generate Cube.js schema files from dbt models with incremental support.

**Options:**
- `--manifest` / `-m`: Path to dbt manifest.json file (required)
- `--catalog` / `-c`: Path to dbt catalog.json file
- `--sqlalchemy-uri` / `-s`: SQLAlchemy database URI for fetching column types
- `--models`: Comma-separated list of model names to process
- `--output` / `-o`: Output directory for Cube.js files (required)
- `--template-dir` / `-t`: Directory containing Cube.js templates (default: ./cube/templates)
- `--state-path`: State file for incremental sync (default: `.dbt-cube-sync-state.json`)
- `--force-full-sync`: Force full regeneration, ignore cached state
- `--no-state`: Disable state tracking (legacy behavior)

**Examples:**
```bash
# Incremental sync (default)
dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/

# Force full rebuild
dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/ --force-full-sync

# Using database connection (no catalog needed)
dbt-cube-sync dbt-to-cube -m manifest.json -s postgresql://user:pass@localhost/db -o output/

# Filter specific models
dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/ --models users,orders
```

---

### `cube-to-bi`

Sync Cube.js schemas to BI tool datasets.

**Arguments:**
- `bi_tool`: BI tool type (`superset`, `tableau`, `powerbi`)

**Options:**
- `--cube-files` / `-c`: Directory containing Cube.js files (required)
- `--url` / `-u`: BI tool URL (required)
- `--username` / `-n`: BI tool username (required)
- `--password` / `-p`: BI tool password (required)
- `--cube-connection-name` / `-d`: Name of Cube database connection in BI tool (default: Cube)

**Example:**
```bash
dbt-cube-sync cube-to-bi superset -c cube_output/ -u http://localhost:8088 -n admin -p admin -d Cube
```

---

## State File

The state file (`.dbt-cube-sync-state.json`) tracks:

```json
{
  "version": "1.0",
  "last_sync_timestamp": "2024-01-15T10:30:00Z",
  "manifest_path": "/path/to/manifest.json",
  "models": {
    "model.project.users": {
      "checksum": "abc123...",
      "has_metrics": true,
      "last_generated": "2024-01-15T10:30:00Z",
      "output_file": "./cube_output/Users.js"
    }
  }
}
```

Delete this file to force a full rebuild, or use `--force-full-sync`.

## Architecture

```
dbt models (with metrics) 
    ↓
dbt-cube-sync generate-cubes
    ↓
Cube.js schemas
    ↓
dbt-cube-sync sync-bi [connector]
    ↓
BI Tool Datasets (Superset/Tableau/PowerBI)
```

### Project Structure

```
dbt-cube-sync/
├── dbt_cube_sync/
│   ├── cli.py                 # CLI interface
│   ├── config.py             # Configuration management
│   ├── core/
│   │   ├── dbt_parser.py     # dbt manifest parser
│   │   ├── db_inspector.py   # Database column type inspector (SQLAlchemy)
│   │   ├── cube_generator.py # Cube.js generator
│   │   ├── cube_validator.py # Docker-based Cube.js schema validator
│   │   └── models.py         # Pydantic data models
│   └── connectors/
│       ├── base.py           # Abstract base connector
│       ├── superset.py       # Superset implementation
│       ├── tableau.py        # Tableau placeholder
│       └── powerbi.py        # PowerBI placeholder
├── Dockerfile                # Container definition
├── pyproject.toml            # Poetry configuration
└── README.md
```

## Adding New BI Connectors

1. Create a new connector class inheriting from `BaseConnector`
2. Implement the required abstract methods
3. Register the connector using `ConnectorRegistry.register()`

Example:
```python
from .base import BaseConnector, ConnectorRegistry

class MyBIConnector(BaseConnector):
    def _validate_config(self):
        # Validation logic
        pass
    
    def connect(self):
        # Connection logic
        pass
    
    def sync_cube_schemas(self, cube_dir):
        # Sync implementation
        pass

# Register the connector
ConnectorRegistry.register('mybi', MyBIConnector)
```

## Docker Integration

The tool is designed to work in containerized environments with proper dependency orchestration:

1. **dbt docs**: Runs `dbt build` then serves documentation
2. **dbt-cube-sync**: Runs sync pipeline after dbt and Cube.js are ready  
3. **BI Tools**: Receive synced datasets after sync completes

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details.