"""Generate and manage embeddings for Cube.js schemas with intelligent document splitting."""

import os
import json
import requests
from typing import List, Dict, Any, Tuple
from pathlib import Path
from collections import defaultdict

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_text_splitters import RecursiveCharacterTextSplitter

from cube_to_rag.core.llm import get_embeddings
from cube_to_rag.core.config import settings


class CubeSplitStrategy:
    """
    Strategy for splitting Cube.js schema documents.

    Uses semantic chunking based on cube structure, then applies
    RecursiveCharacterTextSplitter for any overly large chunks.
    """

    def __init__(self, max_chunk_size: int = 1500, chunk_overlap: int = 200, add_context: bool = True):
        """
        Initialize the split strategy.

        Args:
            max_chunk_size: Maximum size for text chunks (in characters)
            chunk_overlap: Overlap between chunks when splitting large content
            add_context: Whether to add contextual information to chunks
        """
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.add_context = add_context
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )

    def _add_context_to_chunk(self, doc: Document) -> Document:
        """
        Add contextual information to a document chunk.

        This helps the LLM understand the chunk's context during retrieval.

        Args:
            doc: Document to enhance with context

        Returns:
            Document with context prepended
        """
        if not self.add_context:
            return doc

        context_parts = []

        # Add document type context
        doc_type = doc.metadata.get('type', 'unknown')
        if doc_type == 'cube_overview':
            context_parts.append("This is a cube overview containing high-level information.")
        elif doc_type == 'measures':
            cube_name = doc.metadata.get('cube_name', 'unknown')
            context_parts.append(f"These are measures/metrics from the {cube_name} cube.")
        elif doc_type == 'dimensions':
            cube_name = doc.metadata.get('cube_name', 'unknown')
            context_parts.append(f"These are dimensions from the {cube_name} cube for filtering and grouping.")
        elif doc_type in ['catalog_cubes', 'catalog_metrics', 'catalog_dimensions']:
            context_parts.append("This is a complete catalog/summary document.")
        elif doc_type == 'query_guide':
            context_parts.append("This contains GraphQL query patterns and examples.")

        # Add cube name context if available
        cube_name = doc.metadata.get('cube_name')
        cube_camel = doc.metadata.get('cube_name_camel')
        if cube_name and cube_camel:
            context_parts.append(f"Cube: {cube_name} (GraphQL: {cube_camel})")

        # Build context prefix
        if context_parts:
            context_prefix = "CONTEXT: " + " | ".join(context_parts) + "\n\n"
            doc.page_content = context_prefix + doc.page_content

        return doc

    def split_if_needed(self, documents: List[Document]) -> List[Document]:
        """
        Apply RecursiveCharacterTextSplitter to documents that exceed max_chunk_size.

        Args:
            documents: List of semantically chunked documents

        Returns:
            List of documents with large chunks further split and context added
        """
        result = []

        for doc in documents:
            if len(doc.page_content) > self.max_chunk_size:
                # Split large document into smaller chunks
                sub_docs = self.text_splitter.split_documents([doc])

                # Add chunk index to metadata and context
                for idx, sub_doc in enumerate(sub_docs):
                    sub_doc.metadata['chunk_index'] = idx
                    sub_doc.metadata['total_chunks'] = len(sub_docs)
                    sub_doc = self._add_context_to_chunk(sub_doc)
                    result.append(sub_doc)
            else:
                # Add context even if not splitting
                doc = self._add_context_to_chunk(doc)
                result.append(doc)

        return result


class CubeSchemaEmbeddings:
    """Manage Cube.js schema embeddings in Milvus."""

    def __init__(
        self,
        collection_name: str = "cube_schemas",
        split_strategy: CubeSplitStrategy = None,
        max_chunk_size: int = 1500,
        chunk_overlap: int = 200
    ):
        """
        Initialize schema embeddings manager.

        Args:
            collection_name: Name of the Milvus collection
            split_strategy: Custom split strategy (optional)
            max_chunk_size: Maximum chunk size for text splitting
            chunk_overlap: Overlap between chunks
        """
        self.collection_name = collection_name
        self.embeddings = get_embeddings()
        self.vector_store = None
        self.cube_meta_url = f"{settings.cube_api_url}/meta"

        # Initialize split strategy
        self.split_strategy = split_strategy or CubeSplitStrategy(
            max_chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap
        )

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

    def _create_cube_documents(self, cubes: List[Dict[str, Any]]) -> List[Document]:
        """
        Create multiple granular documents for each cube with intelligent splitting.

        Document types created:
        1. Cube overview (high-level info)
        2. Individual measure documents (grouped if many)
        3. Individual dimension documents (grouped if many)
        4. Summary documents (all cubes, metrics catalog, dimensions catalog)
        """
        documents = []
        all_measures = []
        all_dimensions = []
        cube_summaries = []

        for cube_data in cubes:
            cube_name = cube_data.get('name', '')
            cube_title = cube_data.get('title', cube_name)
            cube_name_camel = cube_name[0].lower() + cube_name[1:] if cube_name else cube_name

            # Extract dimensions
            dimensions = []
            for dim in cube_data.get('dimensions', []):
                dim_name = dim['name'].split('.')[-1]
                dim_title = dim.get('shortTitle', dim.get('title', dim_name))
                dim_type = dim.get('type', 'string')
                dimensions.append({
                    'name': dim_name,
                    'title': dim_title,
                    'type': dim_type,
                    'full_name': dim['name']
                })

            # Extract measures
            measures = []
            for measure in cube_data.get('measures', []):
                measure_name = measure['name'].split('.')[-1]
                measure_title = measure.get('shortTitle', measure.get('title', measure_name))
                measure_type = measure.get('aggType', measure.get('type', 'number'))
                measures.append({
                    'name': measure_name,
                    'title': measure_title,
                    'type': measure_type,
                    'full_name': measure['name']
                })

            # 1. CREATE CUBE OVERVIEW DOCUMENT
            dim_names = [d['name'] for d in dimensions]
            measure_names = [m['name'] for m in measures]

            overview_content = f"""CUBE OVERVIEW: {cube_name}

Title: {cube_title}
GraphQL Name: {cube_name_camel}

This cube contains:
- {len(dimensions)} dimensions: {', '.join(dim_names[:10])}{'...' if len(dim_names) > 10 else ''}
- {len(measures)} measures: {', '.join(measure_names[:10])}{'...' if len(measure_names) > 10 else ''}

Use this cube for: {cube_title.lower()}

IMPORTANT: In GraphQL queries, use '{cube_name_camel}' (camelCase), not '{cube_name}'.
"""

            documents.append(Document(
                page_content=overview_content,
                metadata={
                    "cube_name": cube_name,
                    "cube_name_camel": cube_name_camel,
                    "cube_title": cube_title,
                    "type": "cube_overview",
                    "num_dimensions": len(dimensions),
                    "num_measures": len(measures)
                }
            ))

            # 2. CREATE MEASURE DOCUMENTS (individual or small groups)
            for i in range(0, len(measures), 3):  # Group up to 3 measures per document
                measure_group = measures[i:i+3]
                measure_content = f"""MEASURES in {cube_name} ({cube_title})

"""
                for measure in measure_group:
                    measure_content += f"""Measure: {measure['name']}
- Full Name: {measure['full_name']}
- Title: {measure['title']}
- Aggregation Type: {measure['type']}
- Cube: {cube_name_camel} (use this in GraphQL)

GraphQL Example:
query {{
  cube {{
    {cube_name_camel} {{
      {measure['name']}
    }}
  }}
}}

"""
                    all_measures.append({
                        'cube': cube_name,
                        'cube_camel': cube_name_camel,
                        'measure': measure['name'],
                        'title': measure['title'],
                        'type': measure['type']
                    })

                documents.append(Document(
                    page_content=measure_content,
                    metadata={
                        "cube_name": cube_name,
                        "cube_name_camel": cube_name_camel,
                        "cube_title": cube_title,
                        "type": "measures",
                        "num_dimensions": len(dimensions),
                        "num_measures": len(measures),
                        "measure_names": json.dumps([m['name'] for m in measure_group])
                    }
                ))

            # 3. CREATE DIMENSION DOCUMENTS (individual or small groups)
            for i in range(0, len(dimensions), 5):  # Group up to 5 dimensions per document
                dim_group = dimensions[i:i+5]
                dim_content = f"""DIMENSIONS in {cube_name} ({cube_title})

Use these dimensions to filter and group data:

"""
                for dim in dim_group:
                    dim_content += f"""Dimension: {dim['name']}
- Full Name: {dim['full_name']}
- Title: {dim['title']}
- Type: {dim['type']}
- Cube: {cube_name_camel} (use this in GraphQL)

"""
                    all_dimensions.append({
                        'cube': cube_name,
                        'cube_camel': cube_name_camel,
                        'dimension': dim['name'],
                        'title': dim['title'],
                        'type': dim['type']
                    })

                documents.append(Document(
                    page_content=dim_content,
                    metadata={
                        "cube_name": cube_name,
                        "cube_name_camel": cube_name_camel,
                        "cube_title": cube_title,
                        "type": "dimensions",
                        "num_dimensions": len(dimensions),
                        "num_measures": len(measures),
                        "dimension_names": json.dumps([d['name'] for d in dim_group])
                    }
                ))

            # Store cube summary for later
            cube_summaries.append({
                'name': cube_name,
                'name_camel': cube_name_camel,
                'title': cube_title,
                'num_measures': len(measures),
                'num_dimensions': len(dimensions)
            })

        # 4. CREATE SUMMARY DOCUMENTS

        # Summary: All Cubes Catalog
        cubes_catalog = """COMPLETE CUBES CATALOG

This is a comprehensive list of all available data cubes in the system:

"""
        for cube in cube_summaries:
            cubes_catalog += f"""• {cube['name']} (GraphQL: {cube['name_camel']})
  Title: {cube['title']}
  Contains: {cube['num_measures']} measures, {cube['num_dimensions']} dimensions

"""

        documents.append(Document(
            page_content=cubes_catalog,
            metadata={
                "type": "catalog_cubes",
                "cube_name": "",
                "cube_name_camel": "",
                "cube_title": "",
                "num_cubes": len(cube_summaries),
                "num_dimensions": 0,
                "num_measures": 0
            }
        ))

        # Summary: All Metrics/Measures Catalog
        metrics_by_cube = defaultdict(list)
        for m in all_measures:
            metrics_by_cube[m['cube']].append(m)

        metrics_catalog = """COMPLETE METRICS CATALOG

All available measures/metrics organized by cube:

"""
        for cube_name, metrics in metrics_by_cube.items():
            cube_camel = metrics[0]['cube_camel']
            metrics_catalog += f"""\n{cube_name} (GraphQL: {cube_camel}):
"""
            for metric in metrics[:20]:  # Limit to first 20 to avoid too large docs
                metrics_catalog += f"  • {metric['measure']}: {metric['title']} ({metric['type']})\n"
            if len(metrics) > 20:
                metrics_catalog += f"  ... and {len(metrics) - 20} more\n"

        documents.append(Document(
            page_content=metrics_catalog,
            metadata={
                "type": "catalog_metrics",
                "cube_name": "",
                "cube_name_camel": "",
                "cube_title": "",
                "num_metrics": len(all_measures),
                "num_dimensions": 0,
                "num_measures": 0
            }
        ))

        # Summary: All Dimensions Catalog
        dims_by_cube = defaultdict(list)
        for d in all_dimensions:
            dims_by_cube[d['cube']].append(d)

        dims_catalog = """COMPLETE DIMENSIONS CATALOG

All available dimensions for filtering and grouping, organized by cube:

"""
        for cube_name, dims in dims_by_cube.items():
            cube_camel = dims[0]['cube_camel']
            dims_catalog += f"""\n{cube_name} (GraphQL: {cube_camel}):
"""
            for dim in dims[:30]:  # Limit to first 30
                dims_catalog += f"  • {dim['dimension']}: {dim['title']} ({dim['type']})\n"
            if len(dims) > 30:
                dims_catalog += f"  ... and {len(dims) - 30} more\n"

        documents.append(Document(
            page_content=dims_catalog,
            metadata={
                "type": "catalog_dimensions",
                "cube_name": "",
                "cube_name_camel": "",
                "cube_title": "",
                "num_dimensions": len(all_dimensions),
                "num_measures": 0
            }
        ))

        # Summary: GraphQL Query Examples
        query_examples = """GRAPHQL QUERY PATTERNS

Common patterns for querying Cube.js data:

1. Basic Measure Query:
query {
  cube {
    cubeName {
      measureName
    }
  }
}

2. Measure with Dimension (grouping):
query {
  cube {
    cubeName {
      measureName
      dimensionName
    }
  }
}

3. Multiple Measures and Dimensions:
query {
  cube {
    cubeName {
      measure1
      measure2
      dimension1
      dimension2
    }
  }
}

4. Filtering (use where clause):
query {
  cube {
    cubeName(where: {dimensionName: {equals: "value"}}) {
      measureName
      dimensionName
    }
  }
}

IMPORTANT: Always use camelCase cube names in GraphQL queries!

Available Cubes (camelCase names):
"""
        for cube in cube_summaries:
            query_examples += f"- {cube['name_camel']}\n"

        documents.append(Document(
            page_content=query_examples,
            metadata={
                "type": "query_guide",
                "cube_name": "",
                "cube_name_camel": "",
                "cube_title": "",
                "num_dimensions": 0,
                "num_measures": 0
            }
        ))

        return documents

    def ingest_cube_schemas(self, schema_dir: str = None) -> int:
        """
        Ingest Cube.js schemas from API into Milvus with intelligent document splitting.

        Args:
            schema_dir: Unused parameter (kept for API compatibility)

        Returns:
            Number of documents ingested
        """
        # Fetch cubes from Cube.js API
        cubes = self._fetch_cubes_from_api()

        if not cubes:
            print("⚠️  No cubes found from API")
            return 0

        # Create granular documents with semantic splitting
        print("📝 Creating document chunks with semantic splitting...")
        documents = self._create_cube_documents(cubes)

        if not documents:
            print("⚠️  No documents to ingest")
            return 0

        print(f"📊 Semantic chunks created: {len(documents)}")

        # Apply text splitting strategy to handle overly large chunks
        print("✂️  Applying RecursiveCharacterTextSplitter to large chunks...")
        documents = self.split_strategy.split_if_needed(documents)

        print(f"📊 Final document breakdown after splitting:")
        doc_types = defaultdict(int)
        chunk_stats = {'total': 0, 'split': 0, 'original': 0}

        for doc in documents:
            doc_types[doc.metadata.get('type', 'unknown')] += 1
            chunk_stats['total'] += 1
            if 'chunk_index' in doc.metadata:
                chunk_stats['split'] += 1
            else:
                chunk_stats['original'] += 1

        for doc_type, count in doc_types.items():
            print(f"  - {doc_type}: {count}")

        print(f"\n📈 Chunk statistics:")
        print(f"  - Total documents: {chunk_stats['total']}")
        print(f"  - Original chunks: {chunk_stats['original']}")
        print(f"  - Split chunks: {chunk_stats['split']}")

        # Create or update vector store
        self.vector_store = Milvus.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            connection_args=self.connection_args,
            drop_old=True  # Replace existing collection
        )

        print(f"✓ Ingested {len(documents)} documents into Milvus (from {len(cubes)} cubes)")
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

    def as_retriever(self, k: int = 7):
        """
        Get retriever for LangChain.

        Args:
            k: Number of documents to retrieve (default: 7, increased due to document splitting)

        Returns:
            LangChain retriever
        """
        vector_store = self.get_vector_store()
        return vector_store.as_retriever(search_kwargs={"k": k})

    def search_schemas(self, query: str, k: int = 7) -> List[Dict[str, Any]]:
        """
        Search for relevant cube schemas with intelligent document retrieval.

        Args:
            query: Natural language query
            k: Number of results to return (default: 7 due to granular chunking)

        Returns:
            List of relevant schema information
        """
        vector_store = self.get_vector_store()

        # Perform similarity search
        results = vector_store.similarity_search_with_score(query, k=k)

        formatted_results = []
        for doc, score in results:
            result = {
                "type": doc.metadata.get("type", "unknown"),
                "cube_name": doc.metadata.get("cube_name"),
                "content": doc.page_content,
                "relevance_score": float(score),
                "metadata": doc.metadata
            }
            formatted_results.append(result)

        return formatted_results


def get_schema_embeddings() -> CubeSchemaEmbeddings:
    """Factory function to create CubeSchemaEmbeddings instance."""
    return CubeSchemaEmbeddings()
