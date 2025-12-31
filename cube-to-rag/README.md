# Cube-to-RAG

Natural language interface for Cube.js analytics using RAG (Retrieval-Augmented Generation) with vector search and LLM agents.

## Features

- **Semantic Schema Search**: Discover cubes, dimensions, and measures using natural language
- **GraphQL Query Generation**: Automatically build and execute Cube.js GraphQL queries
- **Vector Database**: Store and search schema embeddings in Milvus
- **Multiple LLM Providers**: Support for OpenAI, Anthropic Claude, and AWS Bedrock
- **Streaming Responses**: Real-time token-by-token streaming for better UX
- **FastAPI Backend**: Modern async Python web framework
- **Jinja2 Templates**: Flexible schema formatting

## Architecture

```
User Question
     ↓
1. Semantic Search (Milvus)
   └→ Find relevant cubes, dimensions, measures
     ↓
2. GraphQL Query Construction
   └→ Build query using discovered schema
     ↓
3. Execute Query (Cube.js GraphQL API)
   └→ http://cube_api:4000/cubejs-api/graphql
     ↓
4. Format & Explain Results
   └→ Natural language response
```

## Installation

### Using pip

```bash
pip install cube-to-rag
```

### Using Poetry

```bash
poetry add cube-to-rag
```

### From source

```bash
git clone https://github.com/yourusername/dbt-to-cube.git
cd cube-to-rag
poetry install
```

## Configuration

Create a `.env` file with your configuration:

```bash
# LLM Configuration
LLM_MODEL_ID='anthropic:claude-3-5-sonnet-20241022'  # or 'openai:gpt-4' or 'bedrock:...'
EMBEDDING_MODEL='openai:text-embedding-3-small'  # or 'bedrock:amazon.titan-embed-text-v2:0'

# API Keys (choose based on your LLM/embedding provider)
ANTHROPIC_API_KEY='sk-ant-your-key-here'
OPENAI_API_KEY='sk-your-key-here'

# AWS Bedrock (if using Bedrock models)
AWS_ACCESS_KEY_ID='your-aws-key'
AWS_SECRET_ACCESS_KEY='your-aws-secret'
AWS_DEFAULT_REGION='us-east-1'

# Cube.js Configuration
CUBE_URL='http://cube_api:4000'  # Base URL (GraphQL and REST APIs are auto-constructed)
# Optional: Cube.js API secret (JWT tokens are auto-generated)
# CUBEJS_API_SECRET='your-cubejs-api-secret'

# Milvus Vector Database
MILVUS_SERVER_URI='http://localhost:19530'
# Optional: Milvus authentication (for secured instances)
# MILVUS_USER='root'
# MILVUS_PASSWORD='your-milvus-password'

# Security
SECRET_KEY='your-secret-key-here'
FAST_API_ACCESS_SECRET_TOKEN='your-access-token'
DEPLOY_ENV='local'  # or 'prod'
```

## Quick Start

### 1. Start Required Services

You'll need:
- **Cube.js** running with GraphQL API enabled
- **Milvus** vector database

Using Docker Compose:

```bash
docker-compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml up -d
```

### 2. Run the API Server

```bash
# Using uvicorn directly
uvicorn app.server.main:app --host 0.0.0.0 --port 8080

# Or using the installed package
python -m cube_to_rag
```

### 3. Ingest Cube.js Schemas

The API will automatically fetch and ingest schemas from Cube.js on startup. You can also trigger manual ingestion:

```bash
curl -X POST http://localhost:8080/embeddings/ingest \
  -H "Content-Type: application/json"
```

## Using in Your Own Applications

The `cube-to-rag` package provides tools and utilities you can add to your existing LangChain agents and applications.

### Installation

```bash
pip install cube-to-rag
# or
poetry add cube-to-rag
```

### 1. Add Cube.js Extraction Tool to Your Agent

Add Cube.js querying capabilities to any existing LangChain agent:

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.agent_toolkits.load_tools import load_tools

from cube_to_rag.core.llm import get_llm
from cube_to_rag.tools import get_cube_schema_search_tool

# Your existing tools
your_existing_tools = [...]

# Add Cube.js extraction tools
cube_schema_search = get_cube_schema_search_tool(k=3)

# Use LangChain's built-in GraphQL tool for queries
graphql_tools = load_tools(
    ["graphql"],
    graphql_endpoint="http://localhost:4000/cubejs-api/graphql",
    llm=get_llm()
)

# Combine all tools
tools = your_existing_tools + [cube_schema_search] + graphql_tools

# Create agent with all tools
llm = get_llm()
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to analytics data."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Now your agent can answer questions like:
result = agent_executor.invoke({
    "input": "What's the average course GPA by department?"
})
```

### 2. Add Documents to Milvus Vector Database

Easily embed and store your documents in Milvus:

```python
from langchain_core.documents import Document
from cube_to_rag.tools import create_milvus_helper

# Create helper for your collection
helper = create_milvus_helper(collection_name="my_documents")

# Add documents
docs = [
    Document(
        page_content="Your document content here",
        metadata={"source": "doc1.pdf", "page": 1}
    ),
    Document(
        page_content="More content",
        metadata={"source": "doc2.pdf", "page": 1}
    )
]

ids = helper.add_documents(docs)
print(f"Added {len(ids)} documents to Milvus")

# Or add text directly
texts = ["First document", "Second document"]
metadatas = [{"source": "text1"}, {"source": "text2"}]

ids = helper.add_texts(texts, metadatas)
```

### 3. Add Vector Search Tool to Your Agent

Add semantic document search to any LangChain agent:

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate

from cube_to_rag.core.llm import get_llm
from cube_to_rag.tools import get_vector_search_tool

# Your existing tools
your_existing_tools = [...]

# Add vector search tool
vector_search = get_vector_search_tool(
    collection_name="my_documents",
    k=5
)

# Combine tools
tools = your_existing_tools + [vector_search]

# Create agent
llm = get_llm()
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to document search."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

# Now your agent can search documents
result = agent_executor.invoke({
    "input": "Find documents about machine learning"
})
```

### 4. Complete Example: Agent with All Tools

```python
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.agent_toolkits.load_tools import load_tools

from cube_to_rag.core.llm import get_llm
from cube_to_rag.tools import (
    get_cube_schema_search_tool,
    get_cube_graphql_tools,
    get_vector_search_tool,
    create_milvus_helper
)

# Initialize tools
cube_schema = get_cube_schema_search_tool(k=2)
vector_search = get_vector_search_tool(collection_name="docs", k=3)

# JWT tokens are auto-generated from settings.cube_api_secret
# No need to pass api_token manually - it's handled automatically
graphql_tools = get_cube_graphql_tools(
    graphql_endpoint="http://localhost:4000/cubejs-api/graphql",
    llm=get_llm()
)

tools = [cube_schema, vector_search] + graphql_tools

# Create agent
llm = get_llm()

prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a powerful analytics assistant with access to:

    1. Cube.js analytics (use cube_schema_search FIRST, then graphql)
    2. Document search (use vector_search)

    Always search for relevant schemas/documents before answering."""),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True
)

# Use the agent
result = agent_executor.invoke({
    "input": "What metrics are available for student performance?"
})
print(result["output"])
```

### 5. Working with Milvus Directly

Advanced Milvus operations:

```python
from cube_to_rag.tools import MilvusHelper

# Create helper (uses credentials from environment by default)
helper = MilvusHelper(collection_name="my_collection")

# Or with custom connection arguments (for authentication)
helper_with_auth = MilvusHelper(
    collection_name="my_collection",
    connection_args={
        "uri": "http://localhost:19530",
        "token": "root:your-password"  # Format: username:password
    }
)

# Search with scores
results = helper.search_with_score("machine learning", k=5)
for doc, score in results:
    print(f"Score: {score:.3f} - {doc.page_content}")

# Search with metadata filtering
filtered_results = helper.search(
    query="neural networks",
    k=3,
    filter_dict={"source": "research_papers"}
)

# Get collection statistics
stats = helper.get_collection_stats()
print(f"Total documents: {stats['num_entities']}")

# Delete documents
helper.delete(["id1", "id2", "id3"])
```

### Configuration

Set environment variables or create a `.env` file:

```bash
# LLM Configuration
LLM_MODEL_ID='anthropic:claude-3-5-sonnet-20241022'
EMBEDDING_MODEL='openai:text-embedding-3-small'

# API Keys
ANTHROPIC_API_KEY='your-key'
OPENAI_API_KEY='your-key'

# Cube.js
CUBE_URL='http://localhost:4000'  # Base URL
# Optional: Cube.js authentication (JWT auto-generated from secret)
# CUBEJS_API_SECRET='your-cubejs-api-secret'

# Milvus
MILVUS_SERVER_URI='http://localhost:19530'
# Optional: Milvus authentication (for secured instances)
# MILVUS_USER='root'
# MILVUS_PASSWORD='your-milvus-password'
```

### Available Tools

| Tool | Purpose | Example Use Case |
|------|---------|------------------|
| `get_cube_schema_search_tool()` | Search Cube.js schemas | Discover available cubes/dimensions/measures |
| `get_cube_graphql_tool()` | Execute Cube.js queries | Query analytics data via GraphQL |
| `get_vector_search_tool()` | Search vector database | Find relevant documents semantically |
| `create_milvus_helper()` | Manage Milvus operations | Add/search/delete documents in Milvus |

## API Endpoints

### Chat Endpoints

#### Create Chat Session

```bash
POST /chat/new
```

**Response:**
```json
{
  "status": "success",
  "session_id": "uuid-here"
}
```

#### Ask Question

```bash
POST /chat/ask/
Content-Type: application/json

{
  "message": "What's the average GPA by department?"
}
```

**Response:** Streaming text response

#### Get Chat History

```bash
GET /chat/history
```

#### Clear Chat History

```bash
DELETE /chat/clear
```

### Embeddings Endpoints

#### Ingest Schemas

```bash
POST /embeddings/ingest
Content-Type: application/json

{
  "schema_dir": "/path/to/schemas"  # Optional
}
```

**Response:**
```json
{
  "success": true,
  "schemas_ingested": 5,
  "message": "Successfully ingested 5 cube schemas"
}
```

#### Search Schemas

```bash
POST /embeddings/search?query=course%20performance&k=3
```

**Response:**
```json
{
  "success": true,
  "query": "course performance",
  "results": [
    {
      "cube_name": "CoursePerformanceSummary",
      "dimensions": [...],
      "measures": [...],
      "relevance_score": 0.95
    }
  ]
}
```

#### Health Check

```bash
GET /embeddings/health
```

## Usage Examples

### Python Client

```python
import requests

# Create session
session = requests.Session()
response = session.post(
    "http://localhost:8080/chat/new",
    headers={"x-access-token": "your-token"}
)

# Ask question
response = session.post(
    "http://localhost:8080/chat/ask/",
    headers={"x-access-token": "your-token"},
    json={"message": "What's the average GPA by department?"},
    stream=True
)

# Stream response
for chunk in response.iter_content(chunk_size=1024):
    if chunk:
        print(chunk.decode('utf-8'), end='', flush=True)
```

### JavaScript/TypeScript Client

```typescript
// Create session
const response = await fetch('http://localhost:8080/chat/new', {
  method: 'POST',
  headers: {
    'x-access-token': 'your-token'
  }
});

// Ask question with streaming
const askResponse = await fetch('http://localhost:8080/chat/ask/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'x-access-token': 'your-token'
  },
  body: JSON.stringify({
    message: 'What\'s the average GPA by department?'
  })
});

// Stream response
const reader = askResponse.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(new TextDecoder().decode(value));
}
```

### cURL Examples

```bash
# Create session
curl -X POST http://localhost:8080/chat/new \
  -H "x-access-token: your-token"

# Ask question
curl -X POST http://localhost:8080/chat/ask/ \
  -H "Content-Type: application/json" \
  -H "x-access-token: your-token" \
  -d '{"message": "Show me top 5 courses by enrollment"}' \
  --no-buffer

# Search schemas
curl -X POST "http://localhost:8080/embeddings/search?query=student%20grades&k=2"

# Trigger schema ingestion
curl -X POST http://localhost:8080/embeddings/ingest \
  -H "Content-Type: application/json"
```

## Example Queries

The RAG system can answer questions like:

- "What's the average GPA by department?"
- "Show me course pass rates"
- "Which courses have the highest student engagement?"
- "List all courses with their enrollment numbers"
- "Compare performance across different semesters"
- "What dimensions are available in the data?"
- "Show me all measures I can query"

## How It Works

### 1. Schema Ingestion

On startup, the system:
1. Fetches all cube metadata from Cube.js API (`/cubejs-api/v1/meta`)
2. Extracts cube names, dimensions, measures, and descriptions
3. Generates text embeddings using your configured embedding model
4. Stores embeddings in Milvus for semantic search

### 2. Query Processing

When you ask a question:
1. **Schema Search**: Performs semantic search in Milvus to find relevant cubes
2. **Query Generation**: LLM agent constructs a GraphQL query using discovered schema
3. **Query Execution**: Executes query against Cube.js GraphQL API
4. **Response Formatting**: Formats results into natural language response

### 3. Agent Tools

The LLM agent has access to two tools:

- **`cube_schema_search`**: Semantic search for cubes/dimensions/measures
- **`graphql`**: Execute GraphQL queries against Cube.js

## Supported LLM Providers

### OpenAI

```bash
LLM_MODEL_ID='openai:gpt-4'
# or
LLM_MODEL_ID='openai:gpt-4o-mini'

EMBEDDING_MODEL='openai:text-embedding-3-small'
OPENAI_API_KEY='sk-your-key'
```

### Anthropic Claude

```bash
LLM_MODEL_ID='anthropic:claude-3-5-sonnet-20241022'
EMBEDDING_MODEL='openai:text-embedding-3-small'  # Claude doesn't have embeddings

ANTHROPIC_API_KEY='sk-ant-your-key'
OPENAI_API_KEY='sk-your-key'  # Still needed for embeddings
```

### AWS Bedrock

```bash
LLM_MODEL_ID='bedrock:anthropic.claude-3-5-sonnet-20240620-v1:0'
EMBEDDING_MODEL='bedrock:amazon.titan-embed-text-v2:0'

AWS_ACCESS_KEY_ID='your-key'
AWS_SECRET_ACCESS_KEY='your-secret'
AWS_DEFAULT_REGION='us-east-1'
```

## Development

### Running Tests

```bash
poetry run pytest
```

### Code Formatting

```bash
poetry run black .
poetry run ruff check .
```

## Deployment

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install cube-to-rag

# Copy environment file
COPY .env .env

# Run server
CMD ["uvicorn", "app.server.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Environment Variables

For production, set:

```bash
DEPLOY_ENV='prod'
SECRET_KEY='strong-random-secret'
FAST_API_ACCESS_SECRET_TOKEN='strong-random-token'
```

## Troubleshooting

### Schema search returns no results

```bash
# Check embeddings health
curl http://localhost:8080/embeddings/health

# Re-ingest schemas
curl -X POST http://localhost:8080/embeddings/ingest
```

### GraphQL queries fail

- Verify Cube.js is running: `curl http://localhost:4000/readyz`
- Check cube names use camelCase in GraphQL (e.g., `coursePerformanceSummary` not `CoursePerformanceSummary`)
- Review FastAPI logs: `docker logs cube-rag-api`

### LLM errors

- Verify API keys are set correctly
- Check model IDs match your provider
- Ensure sufficient API credits/quota

