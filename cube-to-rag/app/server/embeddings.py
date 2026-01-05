"""Endpoints for managing cube schema embeddings."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cube_to_rag.core.schema_embeddings import get_schema_embeddings


embeddings_router = APIRouter()


class IngestRequest(BaseModel):
    """Request model for schema ingestion."""
    schema_dir: str = "/workspace/cube_output"


class IngestResponse(BaseModel):
    """Response model for schema ingestion."""
    success: bool
    schemas_ingested: int
    message: str


@embeddings_router.post("/ingest", response_model=IngestResponse)
async def ingest_schemas(request: IngestRequest):
    """
    Ingest Cube.js schema files into Milvus vector store.

    This endpoint reads Cube.js .js schema files from the specified directory,
    generates embeddings, and stores them in Milvus for semantic search.
    """
    try:
        schema_embeddings = get_schema_embeddings()
        count = schema_embeddings.ingest_cube_schemas(request.schema_dir)

        return IngestResponse(
            success=True,
            schemas_ingested=count,
            message=f"Successfully ingested {count} cube schemas"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@embeddings_router.post("/search")
async def search_schemas(query: str, k: int = 3):
    """
    Search for relevant cube schemas using semantic search.

    Args:
        query: Natural language query
        k: Number of results to return (default: 3)
    """
    try:
        schema_embeddings = get_schema_embeddings()
        results = schema_embeddings.search_schemas(query, k=k)

        return {
            "success": True,
            "query": query,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@embeddings_router.get("/health")
async def embeddings_health():
    """Check embeddings service health."""
    try:
        schema_embeddings = get_schema_embeddings()
        vector_store = schema_embeddings.get_vector_store()

        return {
            "status": "healthy",
            "collection": schema_embeddings.collection_name,
            "milvus_uri": schema_embeddings.embeddings
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
