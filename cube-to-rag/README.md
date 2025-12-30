# Cube.js RAG System

A Retrieval-Augmented Generation (RAG) system for Cube.js analytics that enables natural language querying of your data warehouse through vector search and LLMs.

## Features

- **Vector Search**: Uses Milvus for semantic search over Cube.js schemas and metadata
- **LLM Integration**: Supports OpenAI, Anthropic Claude, and AWS Bedrock models
- **Cube.js Query Tool**: Direct integration with Cube.js SQL API for data retrieval
- **FastAPI Backend**: High-performance API for chat and embeddings
- **Streamlit UI**: User-friendly chat interface

## Installation

```bash
poetry install
```

## Configuration

Create a `.private.env` file with your model credentials:

```bash
# LLM Model (choose one)
LLM_MODEL_ID='anthropic:claude-3-5-sonnet-20241022'
# LLM_MODEL_ID='openai:gpt-4'
# LLM_MODEL_ID='bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0'

# Embedding Model
EMBEDDING_MODEL='openai:text-embedding-3-small'

# API Keys
ANTHROPIC_API_KEY='your-anthropic-key'
OPENAI_API_KEY='your-openai-key'

# AWS Credentials (for Bedrock)
# AWS_ACCESS_KEY_ID='your-aws-key'
# AWS_SECRET_ACCESS_KEY='your-aws-secret'
# AWS_DEFAULT_REGION='us-east-1'

# Vector Database
MILVUS_SERVER_URI='http://milvus-standalone:19530'

# Cube.js Connection
CUBE_SQL_HOST='cube_api'
CUBE_SQL_PORT=15432
CUBE_SQL_DATABASE='db'
CUBE_SQL_USER='root'
CUBE_SQL_PASSWORD=''

# Security
SECRET_KEY='your-secret-key'
FAST_API_ACCESS_SECRET_TOKEN='your-access-token'
```

## Usage

### Start the services

```bash
docker-compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml up
```

### Access the UI

- Chat Interface: http://localhost:8501
- Milvus UI (Attu): http://localhost:8000
- FastAPI Docs: http://localhost:8080/docs

## Architecture

1. **Milvus**: Stores vector embeddings of Cube.js schemas and sample queries
2. **FastAPI**: Handles chat requests, embedding generation, and Cube.js queries
3. **LangChain**: Orchestrates RAG pipeline with tools and agents
4. **Streamlit**: Provides chat interface for users
5. **Cube.js**: Data source accessed via SQL API
