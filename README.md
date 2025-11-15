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