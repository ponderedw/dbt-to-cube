"""LangChain tool for searching vector databases."""

from typing import Optional, Dict, Any
from langchain.tools import BaseTool
from pydantic import Field

from cube_to_rag.tools.milvus_helper import MilvusHelper


class VectorSearchTool(BaseTool):
    """Tool for searching documents in Milvus vector database."""

    name: str = "vector_search"
    description: str = """
    Search for relevant documents in a vector database using semantic similarity.

    This tool searches through embedded documents to find the most relevant ones
    based on semantic meaning, not just keyword matching.

    Input should be a natural language query describing what you're looking for.

    Example queries:
    - "machine learning algorithms"
    - "customer feedback about pricing"
    - "technical documentation for API endpoints"

    The tool returns relevant document excerpts with their metadata.
    """

    collection_name: str = Field(default="documents")
    k: int = Field(default=5, description="Number of results to return")
    _helper: Optional[MilvusHelper] = None

    def __init__(self, collection_name: str = "documents", k: int = 5, **kwargs):
        """Initialize vector search tool."""
        super().__init__(collection_name=collection_name, k=k, **kwargs)

    @property
    def helper(self) -> MilvusHelper:
        """Get or create MilvusHelper instance."""
        if self._helper is None:
            self._helper = MilvusHelper(collection_name=self.collection_name)
        return self._helper

    def _run(self, query: str) -> str:
        """Execute vector search."""
        try:
            results = self.helper.search_with_score(query, k=self.k)

            if not results:
                return f"No relevant documents found for query: {query}"

            output = f"Found {len(results)} relevant documents:\n\n"

            for i, (doc, score) in enumerate(results, 1):
                output += f"Document {i} (relevance: {score:.3f}):\n"
                output += f"Content: {doc.page_content}\n"

                if doc.metadata:
                    output += f"Metadata: {doc.metadata}\n"

                output += "\n"

            return output

        except Exception as e:
            return f"Error searching vector database: {str(e)}"

    async def _arun(self, query: str) -> str:
        """Async version of _run."""
        return self._run(query)


def get_vector_search_tool(
    collection_name: str = "documents",
    k: int = 5
) -> VectorSearchTool:
    """
    Factory function to create a vector search tool.

    Args:
        collection_name: Name of the Milvus collection to search
        k: Number of results to return (default: 5)

    Returns:
        VectorSearchTool instance

    Example:
        ```python
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate
        from cube_to_rag.core.llm import get_llm
        from cube_to_rag.tools.vector_search_tool import get_vector_search_tool

        # Create tools
        vector_search = get_vector_search_tool(
            collection_name="my_documents",
            k=3
        )

        # Create agent
        llm = get_llm()
        tools = [vector_search]

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant with access to document search."),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools)

        # Use agent
        result = agent_executor.invoke({
            "input": "Find documents about machine learning"
        })
        ```
    """
    return VectorSearchTool(collection_name=collection_name, k=k)
