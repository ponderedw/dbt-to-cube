"""Main FastAPI application."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.server.chat import chat_router
from app.server.embeddings import embeddings_router
from cube_to_rag.core.config import settings
from cube_to_rag.core.schema_embeddings import get_schema_embeddings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("🚀 Starting Cube.js RAG API...")
    print(f"📊 Cube.js GraphQL API: http://cube_api:4000/cubejs-api/graphql")
    print(f"🔍 Milvus URI: {settings.milvus_server_uri}")
    print(f"🤖 LLM Model: {settings.llm_model_id}")

    # Auto-ingest schemas on startup
    try:
        print("📥 Auto-ingesting Cube.js schemas...")
        schema_embeddings = get_schema_embeddings()
        count = schema_embeddings.ingest_cube_schemas("/workspace/cube_output")
        print(f"✓ Ingested {count} cube schemas into vector store")
    except Exception as e:
        print(f"⚠️  Warning: Could not auto-ingest schemas: {e}")
        print("   Schemas can be manually ingested via POST /embeddings/ingest")

    yield

    # Shutdown
    print("👋 Shutting down Cube.js RAG API...")


app = FastAPI(
    title="Cube.js RAG API",
    description="Natural language interface for Cube.js analytics",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.deploy_env.upper() == 'PROD',
)


@app.middleware("http")
async def check_token_middleware(request: Request, call_next):
    """Verify access token for non-local environments."""
    token = request.headers.get("x-access-token")
    if (settings.deploy_env.upper() != 'LOCAL') and \
       (token != settings.fast_api_access_secret_token):
        return JSONResponse(
            status_code=403,
            content={'reason': 'Invalid or missing token'}
        )
    response = await call_next(request)
    return response


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Cube.js RAG API",
        "version": "0.1.0",
        "endpoints": {
            "chat": "/chat",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


app.include_router(chat_router, prefix='/chat')
app.include_router(embeddings_router, prefix='/embeddings')
