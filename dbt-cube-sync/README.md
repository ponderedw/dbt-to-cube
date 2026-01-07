# dbt-cube-sync

A powerful synchronization tool that creates a seamless pipeline from dbt models to Cube.js schemas and BI tools (Superset, Tableau, PowerBI).

## Features

- 🔄 **dbt → Cube.js**: Auto-generate Cube.js schemas from dbt models with metrics
- 🗃️ **Flexible Data Type Source**: Get column types from catalog OR directly from database via SQLAlchemy
- 🎯 **Model Filtering**: Process specific models instead of all models
- 📊 **Cube.js → BI Tools**: Sync schemas to multiple BI platforms
- 🏗️ **Extensible Architecture**: Plugin-based connector system for easy BI tool integration
- 🐳 **Docker Support**: Containerized execution with orchestration support
- 🎯 **CLI Interface**: Simple command-line tools for automation

## Supported BI Tools

- ✅ **Apache Superset** - Full implementation
- 🚧 **Tableau** - Placeholder (coming soon)
- 🚧 **PowerBI** - Placeholder (coming soon)

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

### `dbt-to-cube`
Generate Cube.js schema files from dbt models.

**Options:**
- `--manifest` / `-m`: Path to dbt manifest.json file (required)
- `--catalog` / `-c`: Path to dbt catalog.json file (optional if --sqlalchemy-uri is provided)
- `--sqlalchemy-uri` / `-s`: SQLAlchemy database URI for fetching column types (optional if --catalog is provided)
  - Example: `postgresql://user:password@localhost:5432/database`
  - Example: `mysql://user:password@localhost:3306/database`
  - Example: `snowflake://user:password@account/database/schema`
- `--models`: Comma-separated list of model names to process (optional, processes all if not specified)
  - Example: `--models model1,model2,model3`
- `--output` / `-o`: Output directory for Cube.js files (required)
- `--template-dir` / `-t`: Directory containing Cube.js templates (default: ./cube/templates)

**Examples:**
```bash
# Using catalog file
dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/

# Using database connection (no catalog needed)
dbt-cube-sync dbt-to-cube -m manifest.json -s postgresql://user:pass@localhost/db -o output/

# Filter specific models
dbt-cube-sync dbt-to-cube -m manifest.json -s postgresql://user:pass@localhost/db --models users,orders -o output/
```

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

### `full-sync`
Complete pipeline: dbt models → Cube.js schemas → BI tool datasets.

**Options:**
- `--dbt-manifest` / `-m`: Path to dbt manifest.json file
- `--cube-dir` / `-c`: Directory for Cube.js files
- `--template-dir` / `-t`: Directory containing Cube.js templates
- `--bi-connector` / `-b`: BI tool to sync to
- `--config-file` / `-f`: Configuration file for BI tool connection

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