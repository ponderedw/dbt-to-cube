"""LangChain tool for searching Cube.js schemas."""

from typing import Optional, Any
from langchain.tools import BaseTool
from langchain.tools.retriever import create_retriever_tool
from langchain_core.prompts import PromptTemplate
from pydantic import Field

from cube_to_rag.core.schema_embeddings import get_schema_embeddings


def get_cube_schema_search_tool(k: int = 7):
    """
    Create a LangChain tool for searching Cube.js schemas.

    This tool enables semantic search through Cube.js cube definitions,
    dimensions, and measures. Documents are split into granular chunks including:
    - Cube overviews
    - Individual measure details
    - Individual dimension details
    - Summary catalogs (all cubes, all metrics, all dimensions)
    - GraphQL query examples

    Use this before querying Cube.js to discover what data is available.

    Args:
        k: Number of relevant documents to return (default: 7, increased for granular chunks)

    Returns:
        LangChain Tool for Cube.js schema search

    Example:
        ```python
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_community.agent_toolkits.load_tools import load_tools

        from cube_to_rag.core.llm import get_llm
        from cube_to_rag.tools.cube_schema_tool import get_cube_schema_search_tool
        from cube_to_rag.tools.cube_graphql_tool import get_cube_graphql_tool

        # Create tools for Cube.js
        schema_search = get_cube_schema_search_tool(k=7)
        graphql_query = get_cube_graphql_tool()

        # Or use LangChain's built-in GraphQL tool
        graphql_tools = load_tools(
            ["graphql"],
            graphql_endpoint="http://localhost:4000/cubejs-api/graphql",
            llm=get_llm()
        )

        tools = [schema_search] + graphql_tools

        # Create agent
        llm = get_llm()

        prompt = ChatPromptTemplate.from_messages([
            ("system", '''You are a Cube.js analytics assistant.

IMPORTANT - Two-Step Process:
1. ALWAYS use cube_schema_search first to discover available cubes/dimensions/measures
2. THEN construct and execute GraphQL queries

Never guess cube names - always search first!'''),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        # Use agent
        result = agent_executor.invoke({
            "input": "What's the average course GPA by department?"
        })
        print(result["output"])
        ```
    """
    # Get schema embeddings
    schema_embeddings = get_schema_embeddings()

    # Create retriever
    retriever = schema_embeddings.as_retriever(k=k)

    # Create retriever tool - page_content already has all formatted info with context
    schema_search_tool = create_retriever_tool(
        retriever,
        "cube_schema_search",
        "Searches and retrieves Cube.js schema information including cube names, dimensions, and measures. "
        "Use this tool FIRST before querying data to discover what cubes, dimensions, and measures are available. "
        "Input should be a natural language description of the data you're looking for "
        "(e.g., 'course performance metrics', 'student enrollment data').",
        document_separator='\n\n---\n\n',
    )

    return schema_search_tool


class CubeSchemaSearchTool(BaseTool):
    """
    Direct tool for searching Cube.js schemas (alternative to retriever tool).

    Use get_cube_schema_search_tool() for better LangChain integration.
    This class is for advanced use cases where you need more control.
    """

    name: str = "cube_schema_search"
    description: str = """
    Search Cube.js schemas to discover available cubes, dimensions, and measures.

    Input: Natural language description of data you're looking for
    Output: Relevant cube schemas with their fields (includes granular chunks like
            cube overviews, measure details, dimension details, and summary catalogs)

    Always use this BEFORE constructing GraphQL queries to discover what's available.
    """

    k: int = Field(default=7, description="Number of results to return")
    _embeddings: Optional[Any] = None

    def __init__(self, k: int = 7, **kwargs):
        """Initialize cube schema search tool."""
        super().__init__(k=k, **kwargs)

    @property
    def embeddings(self):
        """Get or create schema embeddings instance."""
        if self._embeddings is None:
            self._embeddings = get_schema_embeddings()
        return self._embeddings

    def _run(self, query: str) -> str:
        """Execute schema search."""
        try:
            results = self.embeddings.search_schemas(query, k=self.k)

            if not results:
                return f"No Cube.js schemas found for: {query}"

            output = f"Found {len(results)} relevant Cube.js schemas:\n\n"

            for i, result in enumerate(results, 1):
                output += f"Schema {i}:\n"
                output += f"Cube: {result.get('cube_name', 'Unknown')}\n"

                dimensions = result.get('dimensions', [])
                if dimensions:
                    output += f"Dimensions: {', '.join(dimensions)}\n"

                measures = result.get('measures', [])
                if measures:
                    output += f"Measures: {', '.join(measures)}\n"

                description = result.get('description', '')
                if description:
                    output += f"Description: {description}\n"

                output += "\n"

            return output

        except Exception as e:
            return f"Error searching Cube.js schemas: {str(e)}"

    async def _arun(self, query: str) -> str:
        """Async version of _run."""
        return self._run(query)
