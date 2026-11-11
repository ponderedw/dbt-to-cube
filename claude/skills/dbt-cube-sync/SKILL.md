---
name: dbt-cube-sync
description: How to install and run dbt-cube-sync to generate Cube.js schemas from dbt models and sync them to BI tools
---

# dbt-cube-sync

Converts dbt models to Cube.js schemas. Reads `manifest.json` (and optionally `catalog.json`) directly — no dbt runtime needed. Syncs generated schemas to Superset, Tableau, and PowerBI.

## Installation

```bash
pip install dbt-cube-sync
# or in a Poetry project:
poetry add dbt-cube-sync
```

For database-based column type resolution, also install the driver:
```bash
pip install psycopg2-binary   # PostgreSQL
pip install snowflake-sqlalchemy  # Snowflake
pip install sqlalchemy-bigquery   # BigQuery
```

## Commands

### `sync-all` — full incremental pipeline (recommended)

```bash
dbt-cube-sync sync-all \
  --manifest ./target/manifest.json \
  --catalog  ./target/catalog.json \
  --output   ./cube_output

# with Superset sync
dbt-cube-sync sync-all \
  --manifest ./target/manifest.json \
  --catalog  ./target/catalog.json \
  --output   ./cube_output \
  --superset-url      http://localhost:8088 \
  --superset-username admin \
  --superset-password admin

# skip catalog, use live DB instead
dbt-cube-sync sync-all \
  --manifest       ./target/manifest.json \
  --sqlalchemy-uri postgresql://user:pass@localhost:5432/mydb \
  --output         ./cube_output

# force full rebuild (ignore cached state)
dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output --force-full-sync
```

| Option | Required | Description |
|--------|----------|-------------|
| `--manifest` / `-m` | Yes | Path to `manifest.json` |
| `--catalog` / `-c` | No* | Path to `catalog.json` |
| `--sqlalchemy-uri` / `-s` | No* | DB URI for column types |
| `--output` / `-o` | Yes | Output directory |
| `--state-path` | No | State file (default: `.dbt-cube-sync-state.json`) |
| `--force-full-sync` | No | Rebuild everything, ignore state |
| `--superset-url` | No | Superset base URL |
| `--superset-username` | No | Superset username |
| `--superset-password` | No | Superset password |
| `--cube-connection-name` | No | Cube connection name in Superset (default: `Cube`) |
| `--rag-api-url` | No | RAG API for embedding updates |

*Either `--catalog` or `--sqlalchemy-uri` is required.

### `dbt-to-cube` — Cube.js generation only

```bash
dbt-cube-sync dbt-to-cube \
  --manifest ./target/manifest.json \
  --catalog  ./target/catalog.json \
  --output   ./cube_output

# filter to specific models
dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/ \
  --models attendance_by_student_date,enrollment_summary
```

### `cube-to-bi` — BI sync only

```bash
dbt-cube-sync cube-to-bi superset \
  --cube-files ./cube_output \
  --url        http://localhost:8088 \
  --username   admin \
  --password   admin \
  --cube-connection-name Cube
```

## Incremental state

State is stored in `.dbt-cube-sync-state.json`. On each run the tool:
1. Checksums every node in `manifest.json`
2. Compares against stored checksums
3. Regenerates only changed/added models; deletes `.js` files for removed models
4. Updates the state file

Delete the state file (or pass `--force-full-sync`) to trigger a full rebuild.

## Which models get picked up

A model is included if it has at least one metric defined. Three formats are supported — see the `dbt-semantic-layer` skill for the full reference.

## Column type resolution priority

1. `data_type:` explicitly set in the model's `.yml` column definition
2. `catalog.json` (from `dbt docs generate`)
3. Live database via `--sqlalchemy-uri`

If none of the above supply a type, the column defaults to `string`.
