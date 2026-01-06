"""Wrapper for LangChain's GraphQL tool with Cube.js-specific configuration and retry logic."""

import json
import time
from typing import List, Optional, Any, Dict
from langchain.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from pydantic import Field


# Cube.js-specific instructions for the agent prompt
CUBE_GRAPHQL_INSTRUCTIONS = """

CRITICAL - Two-Step Process:
1. ALWAYS use cube_schema_search tool FIRST to discover available cubes, dimensions, and measures
2. THEN use cube_graphql_query tool with the EXACT field names from the search results

⚠️ FIELD NAME RULES - EXTREMELY IMPORTANT:
- Use EXACT field names AS SHOWN in the schema search results
- DO NOT convert snake_case to camelCase or vice versa
- DO NOT guess or modify field names
- If search shows "school_year", use "school_year" (NOT "schoolYear")
- If search shows "studentId", use "studentId" (NOT "student_id")
- Copy field names EXACTLY character-by-character from the retrieved schema

GraphQL Query Format for Cube.js:

Basic query:
query {{
  cube {{
    cubeName {{
      exact_measure_name
      exact_dimension_name
      timeDimension {{
        year
        month
      }}
    }}
  }}
}}

Query with filtering (use 'where' clause):
query CubeQuery {{
  cube(
    where: {{cubeName: {{dimension_name: {{in: ["value1", "value2"]}}}}}}
  ) {{
    cubeName {{
      dimension_name
      measure_name
    }}
  }}
}}

Real example with filtering:
query CubeQuery {{
  cube(
    where: {{coursePerformanceSummary: {{instructor_name: {{in: ["Emily Davis", "John Smith"]}}}}}}
  ) {{
    coursePerformanceSummary {{
      course_code
      course_name
      department_name
      excellence_rate_percentage
      performance_category
      semester_end_date {{
        value
        year
      }}
    }}
  }}
}}

Example workflow:
User: "What school years are available?"
1. Search: cube_schema_search("school year")
2. Retrieved schema shows: dimension "school_year" (note the underscore!)
3. Query: Use "school_year" EXACTLY as shown - DO NOT change to "schoolYear"
4. Explain results

NOTE: The cube_graphql_query tool now has built-in retry logic for "Continue wait" errors.
When Cube.js is building pre-aggregations, the tool will automatically wait and retry.
You don't need to handle this manually - just call the tool and it will handle retries.

REMEMBER: The cube_graphql_query tool will fail if you use incorrect field names.
Always copy field names EXACTLY from the schema search results."""


class CubeGraphQLToolWithRetry(BaseTool):
    """
    GraphQL tool for Cube.js with automatic retry logic for 'Continue wait' errors.

    This tool wraps the GraphQL API and automatically handles pre-aggregation building delays.
    """

    name: str = "cube_graphql_query"
    description: str = """
    Execute GraphQL queries against Cube.js to retrieve analytics data.

    This tool has built-in retry logic for pre-aggregation building.

    Input should be a valid GraphQL query string.

    IMPORTANT: Always use cube_schema_search tool first to discover available fields.
    Use EXACT field names from the schema search results.

    Example query structure:
    query {
      cube {
        cubeName {
          measureName
          dimensionName
        }
      }
    }
    """

    graphql_endpoint: str = Field(default="http://cube_api:4000/cubejs-api/graphql")
    custom_headers: Optional[Dict[str, str]] = Field(default=None)
    max_retries: int = Field(default=3)
    retry_delay: int = Field(default=5)

    def _execute_graphql_query(self, query: str) -> Dict[str, Any]:
        """Execute a GraphQL query using gql library."""
        try:
            from gql import Client, gql
            from gql.transport.requests import RequestsHTTPTransport
        except ImportError as e:
            raise ImportError(
                "Could not import gql python package. "
                f"Try installing it with `pip install gql`. Received error: {e}"
            )

        # Create transport
        transport = RequestsHTTPTransport(
            url=self.graphql_endpoint,
            headers=self.custom_headers or {},
        )

        # Create client
        client = Client(
            transport=transport,
            fetch_schema_from_transport=True
        )

        # Execute query
        document_node = gql(query)
        result = client.execute(document_node)
        return result

    def _is_continue_wait_error(self, result: Dict[str, Any]) -> bool:
        """Check if the result contains a 'Continue wait' error."""
        if "errors" in result:
            for error in result["errors"]:
                if isinstance(error, dict) and error.get("message", "").lower() == "continue wait":
                    return True
        return False

    def _run(
        self,
        query: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute GraphQL query with automatic retry for 'Continue wait' errors."""

        for attempt in range(self.max_retries):
            try:
                # Execute the query
                result = self._execute_graphql_query(query)

                # Check for 'Continue wait' error
                if self._is_continue_wait_error(result):
                    if attempt < self.max_retries - 1:
                        # Log the retry attempt
                        wait_time = self.retry_delay * (attempt + 1)
                        print(f"[Cube.js] Received 'Continue wait' - pre-aggregations building. Retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})...")
                        time.sleep(wait_time)
                        continue
                    else:
                        # Max retries reached
                        return json.dumps({
                            "error": "Continue wait",
                            "message": "Cube.js is still building pre-aggregations after multiple retries. Please try again in 30-60 seconds.",
                            "attempts": self.max_retries
                        }, indent=2)

                # Check for other errors
                if "errors" in result and not result.get("data"):
                    errors = result["errors"]
                    error_messages = [err.get("message", str(err)) for err in errors]
                    return json.dumps({
                        "error": "GraphQL Error",
                        "messages": error_messages,
                        "details": errors
                    }, indent=2)

                # Success - return the data
                return json.dumps(result, indent=2)

            except Exception as e:
                # Handle connection or other errors
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    print(f"[Cube.js] Query failed with error: {str(e)}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    return json.dumps({
                        "error": "Query execution failed",
                        "message": str(e),
                        "attempts": self.max_retries
                    }, indent=2)

        # Should never reach here, but just in case
        return json.dumps({
            "error": "Max retries exceeded",
            "attempts": self.max_retries
        }, indent=2)

    async def _arun(
        self,
        query: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Async version - calls sync version for now."""
        return self._run(query, run_manager)


def get_cube_graphql_tools(
    graphql_endpoint: str = "http://cube_api:4000/cubejs-api/graphql",
    llm=None,
    api_token: str = None,
    max_retries: int = 3,
    retry_delay: int = 5
) -> List[BaseTool]:
    """
    Get GraphQL tool configured for Cube.js with automatic retry logic.

    This function creates a custom GraphQL tool that automatically handles
    "Continue wait" errors from Cube.js during pre-aggregation building.

    Args:
        graphql_endpoint: Cube.js GraphQL API endpoint URL
        llm: LangChain LLM instance (not used, kept for compatibility)
        api_token: Optional Cube.js API token for authentication
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Base delay between retries in seconds (default: 5)

    Returns:
        List containing the Cube.js GraphQL tool with retry logic

    Example:
        ```python
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate

        from cube_to_rag.core.llm import get_llm
        from cube_to_rag.tools import get_cube_schema_search_tool, get_cube_graphql_tools

        # Create tools
        schema_search = get_cube_schema_search_tool(k=5)
        graphql_tools = get_cube_graphql_tools(
            graphql_endpoint="http://localhost:4000/cubejs-api/graphql",
            max_retries=3,
            retry_delay=5
        )

        tools = [schema_search] + graphql_tools

        # Create agent
        llm = get_llm()

        prompt = ChatPromptTemplate.from_messages([
            ("system", '''You are a Cube.js analytics assistant.

IMPORTANT - Two-Step Process:
1. ALWAYS use cube_schema_search first to discover cubes/dimensions/measures
2. THEN use cube_graphql_query to execute queries

The GraphQL tool has automatic retry logic for pre-aggregation building.'''),
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
    # Build custom headers if API token is provided
    custom_headers = {}
    if api_token:
        custom_headers["Authorization"] = api_token

    # Create the custom tool with retry logic
    tool = CubeGraphQLToolWithRetry(
        graphql_endpoint=graphql_endpoint,
        custom_headers=custom_headers if custom_headers else None,
        max_retries=max_retries,
        retry_delay=retry_delay
    )

    return [tool]
