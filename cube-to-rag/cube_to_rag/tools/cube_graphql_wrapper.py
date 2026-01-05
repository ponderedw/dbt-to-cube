"""Wrapper for LangChain's GraphQL tool with Cube.js-specific configuration."""

from typing import List
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain.tools import BaseTool


# Cube.js-specific instructions for the agent prompt
CUBE_GRAPHQL_INSTRUCTIONS = """

IMPORTANT - Two-Step Process:
1. ALWAYS use cube_schema_search tool FIRST to discover available cubes, dimensions, and measures
2. THEN use cube_graphql_query tool to execute the query

GraphQL Query Format for Cube.js:
query {{
  cube {{
    cubeName {{
      measureName
      dimensionName
      timeDimension {{
        year
        month
      }}
    }}
  }}
}}

Example workflow:
User: "What's the average GPA?"
1. Search: cube_schema_search("average GPA grades performance")
2. Discover: CoursePerformanceSummary cube with average_course_gpa measure
3. Query: cube_graphql_query with proper GraphQL syntax
4. Explain results

The cube_graphql_query tool already knows how to construct Cube.js GraphQL queries.
Never guess cube names - always discover them first through search."""


def get_cube_graphql_tools(
    graphql_endpoint: str = "http://cube_api:4000/cubejs-api/graphql",
    llm=None,
    api_token: str = None
) -> List[BaseTool]:
    """
    Get LangChain's GraphQL tool configured for Cube.js with proper description.

    This function wraps LangChain's built-in GraphQL tool and enhances it with
    Cube.js-specific instructions and description.

    Args:
        graphql_endpoint: Cube.js GraphQL API endpoint URL
        llm: LangChain LLM instance (optional, will use from config if not provided)
        api_token: Optional Cube.js API token for authentication

    Returns:
        List of LangChain tools configured for Cube.js GraphQL queries

    Example:
        ```python
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate

        from cube_to_rag.core.llm import get_llm
        from cube_to_rag.tools import get_cube_schema_search_tool, get_cube_graphql_tools

        # Create tools
        schema_search = get_cube_schema_search_tool(k=2)
        graphql_tools = get_cube_graphql_tools(
            graphql_endpoint="http://localhost:4000/cubejs-api/graphql"
            # JWT tokens are auto-generated from CUBEJS_API_SECRET
        )

        tools = [schema_search] + graphql_tools

        # Create agent
        llm = get_llm()

        prompt = ChatPromptTemplate.from_messages([
            ("system", '''You are a Cube.js analytics assistant.

IMPORTANT - Two-Step Process:
1. ALWAYS use cube_schema_search first to discover cubes/dimensions/measures
2. THEN use the GraphQL tool to execute queries

The GraphQL tool already knows how to construct Cube.js queries.'''),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_tool_calling_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        # Use agent
        result = agent_executor.invoke({
            "input": "What's the average course GPA by department?"
        })
        ```
    """
    if llm is None:
        from cube_to_rag.core.llm import get_llm
        llm = get_llm()

    # Build custom headers if API token is provided
    custom_headers = {}
    if api_token:
        custom_headers["Authorization"] = api_token

    # Load LangChain's built-in GraphQL tool
    load_tool_kwargs = {
        "graphql_endpoint": graphql_endpoint,
        "llm": llm
    }

    # Add custom headers if token is provided
    if custom_headers:
        load_tool_kwargs["custom_headers"] = custom_headers

    graphql_tools = load_tools(["graphql"], **load_tool_kwargs)

    # Rename the tool to be more specific
    if graphql_tools:
        graphql_tools[0].name = "cube_graphql_query"

    return graphql_tools
