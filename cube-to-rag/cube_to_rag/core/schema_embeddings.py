"""Generate and manage embeddings for Cube.js schemas."""

import os
import json
import requests
from typing import List, Dict, Any
from pathlib import Path

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain.text_splitter import RecursiveCharacterTextSplitter

from cube_to_rag.core.llm import get_embeddings
from cube_to_rag.core.config import settings


class CubeSchemaEmbeddings:
    """Manage Cube.js schema embeddings in Milvus."""

    def __init__(self, collection_name: str = "cube_schemas"):
        """Initialize schema embeddings manager."""
        self.collection_name = collection_name
        self.embeddings = get_embeddings()
        self.vector_store = None
        self.cube_meta_url = f"{settings.cube_api_url}/meta"

        # Build Milvus connection args with authentication if provided
        self.connection_args = {"uri": settings.milvus_server_uri}
        if settings.milvus_password:
            self.connection_args["token"] = f"{settings.milvus_user}:{settings.milvus_password}"

    def _fetch_cubes_from_api(self) -> List[Dict[str, Any]]:
        """Fetch cube metadata from Cube.js API."""
        try:
            print(f"📡 Fetching metadata from {self.cube_meta_url}")

            # Build headers with authentication if token is provided
            headers = {}
            if settings.cube_api_token:
                headers["Authorization"] = settings.cube_api_token

            response = requests.get(self.cube_meta_url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            cubes = data.get('cubes', [])

            print(f"✓ Found {len(cubes)} cubes from API")
            return cubes
        except Exception as e:
            print(f"❌ Error fetching from Cube.js API: {e}")
            raise

    def ingest_cube_schemas(self, schema_dir: str = None) -> int:
        """
        Ingest Cube.js schemas from API into Milvus.

        Args:
            schema_dir: Unused parameter (kept for API compatibility)

        Returns:
            Number of schemas ingested
        """
        # Fetch cubes from Cube.js API
        cubes = self._fetch_cubes_from_api()

        if not cubes:
            print("⚠️  No cubes found from API")
            return 0

        documents = []

        # Process each cube from API
        for cube_data in cubes:
            cube_name = cube_data.get('name', '')
            cube_title = cube_data.get('title', cube_name)

            # Extract dimensions with descriptions
            dimensions = []
            dimension_details = []
            for dim in cube_data.get('dimensions', []):
                dim_name = dim['name'].split('.')[-1]  # Remove cube prefix
                dim_title = dim.get('shortTitle', dim.get('title', dim_name))
                dimensions.append(dim_name)
                dimension_details.append(f"- {dim_name}: {dim_title} ({dim.get('type', 'string')})")

            # Extract measures with descriptions
            measures = []
            measure_details = []
            for measure in cube_data.get('measures', []):
                measure_name = measure['name'].split('.')[-1]  # Remove cube prefix
                measure_title = measure.get('shortTitle', measure.get('title', measure_name))
                measure_type = measure.get('aggType', measure.get('type', 'number'))
                measures.append(measure_name)
                measure_details.append(f"- {measure_name}: {measure_title} (aggregation: {measure_type})")

            # Convert cube name to camelCase for GraphQL
            cube_name_camel = cube_name[0].lower() + cube_name[1:] if cube_name else cube_name

            # Create comprehensive text representation for embedding
            text_content = f"""
Cube: {cube_name}
GraphQL Cube Name: {cube_name_camel}
Title: {cube_title}

Available Dimensions:
{chr(10).join(dimension_details) if dimension_details else 'None'}

Available Measures:
{chr(10).join(measure_details) if measure_details else 'None'}

GraphQL Query Example:
query {{
  cube {{
    {cube_name_camel} {{
      {chr(10).join(f"      {measure}" for measure in measures[:3])}
      {chr(10).join(f"      {dim}" for dim in dimensions[:3])}
    }}
  }}
}}

IMPORTANT: Always use '{cube_name_camel}' (camelCase) in GraphQL queries, not '{cube_name}'.

Use this cube for queries about: {cube_title.lower()}
"""

            # Create metadata for filtering
            metadata = {
                "cube_name": cube_name,
                "cube_title": cube_title,
                "dimensions": json.dumps(dimensions),
                "measures": json.dumps(measures),
                "type": "cube_schema"
            }

            doc = Document(
                page_content=text_content,
                metadata=metadata
            )
            documents.append(doc)

        if not documents:
            print("⚠️  No documents to ingest")
            return 0

        # Create or update vector store
        self.vector_store = Milvus.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            connection_args=self.connection_args,
            drop_old=True  # Replace existing collection
        )

        print(f"✓ Ingested {len(documents)} cube schemas into Milvus")
        return len(documents)

    def get_vector_store(self) -> Milvus:
        """Get or create vector store instance."""
        if self.vector_store is None:
            self.vector_store = Milvus(
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
                connection_args=self.connection_args
            )
        return self.vector_store

    def as_retriever(self, k: int = 2):
        """
        Get retriever for LangChain.

        Args:
            k: Number of documents to retrieve

        Returns:
            LangChain retriever
        """
        vector_store = self.get_vector_store()
        return vector_store.as_retriever(search_kwargs={"k": k})

    def search_schemas(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Search for relevant cube schemas.

        Args:
            query: Natural language query
            k: Number of results to return

        Returns:
            List of relevant schema information
        """
        vector_store = self.get_vector_store()

        # Perform similarity search
        results = vector_store.similarity_search_with_score(query, k=k)

        formatted_results = []
        for doc, score in results:
            result = {
                "cube_name": doc.metadata.get("cube_name"),
                "dimensions": json.loads(doc.metadata.get("dimensions", "[]")),
                "measures": json.loads(doc.metadata.get("measures", "[]")),
                "content": doc.page_content,
                "relevance_score": float(score)
            }
            formatted_results.append(result)

        return formatted_results


def get_schema_embeddings() -> CubeSchemaEmbeddings:
    """Factory function to create CubeSchemaEmbeddings instance."""
    return CubeSchemaEmbeddings()
