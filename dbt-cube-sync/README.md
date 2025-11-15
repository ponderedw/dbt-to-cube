# dbt-cube-sync

A powerful synchronization tool that creates a seamless pipeline from dbt models to Cube.js schemas and BI tools (Superset, Tableau, PowerBI).

## Features

- 🔄 **dbt → Cube.js**: Auto-generate Cube.js schemas from dbt models with metrics
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

### Using Docker

```bash
docker build -t dbt-cube-sync .
docker run --rm dbt-cube-sync --help
```

## Quick Start

### 1. Create Configuration File

```bash
# Create sample config
dbt-cube-sync create-config sync-config.yaml

# Edit the config file with your BI tool credentials
```

### 2. Generate Cube.js Schemas

```bash
# Generate from dbt manifest
dbt-cube-sync generate-cubes \\
  --dbt-manifest ./DbtEducationalDataProject/target/manifest.json \\
  --output-dir ./cube/conf/cube_output
```

### 3. Sync to BI Tool

```bash
# Sync to Superset
dbt-cube-sync sync-bi superset \\
  --cube-dir ./cube/conf/cube_output \\
  --config-file ./sync-config.yaml
```

### 4. Full Pipeline

```bash
# Complete dbt → Cube.js → Superset pipeline
dbt-cube-sync full-sync \\
  --dbt-manifest ./DbtEducationalDataProject/target/manifest.json \\
  --cube-dir ./cube/conf/cube_output \\
  --bi-connector superset \\
  --config-file ./sync-config.yaml
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

### `generate-cubes`
Generate Cube.js schema files from dbt models.

**Options:**
- `--dbt-manifest` / `-m`: Path to dbt manifest.json file
- `--output-dir` / `-o`: Output directory for Cube.js files
- `--template-dir` / `-t`: Directory containing Cube.js templates

### `sync-bi`
Sync Cube.js schemas to BI tool datasets.

**Arguments:**
- `connector`: BI tool type (`superset`, `tableau`, `powerbi`)

**Options:**
- `--cube-dir` / `-c`: Directory containing Cube.js files
- `--config-file` / `-f`: Configuration file for BI tool connection

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