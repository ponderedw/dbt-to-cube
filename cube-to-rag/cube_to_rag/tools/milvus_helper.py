"""Helper functions for working with Milvus vector database."""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from langchain_milvus import Milvus

from cube_to_rag.core.llm import get_embeddings
from cube_to_rag.core.config import settings


class MilvusHelper:
    """Helper class for Milvus vector database operations."""

    def __init__(
        self,
        collection_name: str = "cube_schemas",
        connection_args: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize Milvus helper.

        Args:
            collection_name: Name of the Milvus collection
            connection_args: Optional connection arguments for Milvus
        """
        self.collection_name = collection_name

        # Build default connection args with authentication if provided
        if connection_args is None:
            default_args = {"uri": settings.milvus_server_uri}

            # Add authentication if password is set
            if settings.milvus_password:
                default_args["token"] = f"{settings.milvus_user}:{settings.milvus_password}"

            self.connection_args = default_args
        else:
            self.connection_args = connection_args

        self.embeddings = get_embeddings()
        self._vector_store = None

    @property
    def vector_store(self) -> Milvus:
        """Get or create vector store instance."""
        if self._vector_store is None:
            self._vector_store = Milvus(
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
                connection_args=self.connection_args,
                auto_id=True,
            )
        return self._vector_store

    def add_documents(
        self,
        documents: List[Document],
        batch_size: int = 100
    ) -> List[str]:
        """
        Add documents to Milvus vector store.

        Args:
            documents: List of LangChain Document objects to add
            batch_size: Number of documents to process at once

        Returns:
            List of document IDs

        Example:
            ```python
            from langchain_core.documents import Document
            from cube_to_rag.tools.milvus_helper import MilvusHelper

            helper = MilvusHelper(collection_name="my_collection")

            docs = [
                Document(
                    page_content="Content here",
                    metadata={"source": "doc1", "type": "text"}
                ),
                Document(
                    page_content="More content",
                    metadata={"source": "doc2", "type": "text"}
                )
            ]

            ids = helper.add_documents(docs)
            print(f"Added {len(ids)} documents")
            ```
        """
        ids = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            batch_ids = self.vector_store.add_documents(batch)
            ids.extend(batch_ids)
        return ids

    def add_texts(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        batch_size: int = 100
    ) -> List[str]:
        """
        Add text documents to Milvus vector store.

        Args:
            texts: List of text strings to add
            metadatas: Optional list of metadata dictionaries for each text
            batch_size: Number of texts to process at once

        Returns:
            List of document IDs

        Example:
            ```python
            from cube_to_rag.tools.milvus_helper import MilvusHelper

            helper = MilvusHelper(collection_name="my_collection")

            texts = ["First document", "Second document"]
            metadatas = [{"source": "doc1"}, {"source": "doc2"}]

            ids = helper.add_texts(texts, metadatas)
            ```
        """
        ids = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_metas = metadatas[i:i + batch_size] if metadatas else None
            batch_ids = self.vector_store.add_texts(
                texts=batch_texts,
                metadatas=batch_metas
            )
            ids.extend(batch_ids)
        return ids

    def search(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Search for similar documents in Milvus.

        Args:
            query: Search query string
            k: Number of results to return
            filter_dict: Optional metadata filter

        Returns:
            List of Document objects with similarity scores

        Example:
            ```python
            from cube_to_rag.tools.milvus_helper import MilvusHelper

            helper = MilvusHelper(collection_name="my_collection")
            results = helper.search("machine learning", k=3)

            for doc in results:
                print(f"Content: {doc.page_content}")
                print(f"Metadata: {doc.metadata}")
            ```
        """
        if filter_dict:
            return self.vector_store.similarity_search(
                query,
                k=k,
                expr=self._build_filter_expr(filter_dict)
            )
        return self.vector_store.similarity_search(query, k=k)

    def search_with_score(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[tuple[Document, float]]:
        """
        Search for similar documents with relevance scores.

        Args:
            query: Search query string
            k: Number of results to return
            filter_dict: Optional metadata filter

        Returns:
            List of (Document, score) tuples

        Example:
            ```python
            from cube_to_rag.tools.milvus_helper import MilvusHelper

            helper = MilvusHelper(collection_name="my_collection")
            results = helper.search_with_score("data analysis", k=3)

            for doc, score in results:
                print(f"Score: {score:.4f}")
                print(f"Content: {doc.page_content}")
            ```
        """
        if filter_dict:
            return self.vector_store.similarity_search_with_score(
                query,
                k=k,
                expr=self._build_filter_expr(filter_dict)
            )
        return self.vector_store.similarity_search_with_score(query, k=k)

    def delete(self, ids: List[str]) -> bool:
        """
        Delete documents by IDs.

        Args:
            ids: List of document IDs to delete

        Returns:
            True if successful

        Example:
            ```python
            from cube_to_rag.tools.milvus_helper import MilvusHelper

            helper = MilvusHelper(collection_name="my_collection")
            helper.delete(["id1", "id2", "id3"])
            ```
        """
        self.vector_store.delete(ids)
        return True

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the collection.

        Returns:
            Dictionary with collection statistics

        Example:
            ```python
            from cube_to_rag.tools.milvus_helper import MilvusHelper

            helper = MilvusHelper(collection_name="my_collection")
            stats = helper.get_collection_stats()
            print(f"Total documents: {stats['num_entities']}")
            ```
        """
        try:
            collection = self.vector_store.col
            collection.load()
            return {
                "num_entities": collection.num_entities,
                "collection_name": self.collection_name,
            }
        except Exception as e:
            return {
                "error": str(e),
                "collection_name": self.collection_name,
            }

    @staticmethod
    def _build_filter_expr(filter_dict: Dict[str, Any]) -> str:
        """Build Milvus filter expression from dictionary."""
        expressions = []
        for key, value in filter_dict.items():
            if isinstance(value, str):
                expressions.append(f'{key} == "{value}"')
            else:
                expressions.append(f'{key} == {value}')
        return " && ".join(expressions) if expressions else ""


def create_milvus_helper(
    collection_name: str = "cube_schemas",
    connection_args: Optional[Dict[str, Any]] = None
) -> MilvusHelper:
    """
    Factory function to create MilvusHelper instance.

    Args:
        collection_name: Name of the Milvus collection
        connection_args: Optional connection arguments

    Returns:
        MilvusHelper instance

    Example:
        ```python
        from cube_to_rag.tools.milvus_helper import create_milvus_helper

        helper = create_milvus_helper(collection_name="my_docs")
        ```
    """
    return MilvusHelper(
        collection_name=collection_name,
        connection_args=connection_args
    )
