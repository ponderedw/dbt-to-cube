"""LangChain tool for querying Cube.js via GraphQL API."""

import requests
from typing import Optional
from langchain.tools import BaseTool
from pydantic import Field

from cube_to_rag.core.config import settings


class CubeGraphQLTool(BaseTool):
    """Tool for executing GraphQL queries against Cube.js API."""

    name: str = "cube_graphql_query"
    description: str = """
    Execute GraphQL queries against Cube.js to retrieve analytics data.

    This tool queries the Cube.js GraphQL API to get aggregated analytics data.

    Input should be a valid GraphQL query string.

    IMPORTANT: Do NOT guess cube names, dimensions, or measures.
    Always use the cube_schema_search tool first to discover available cubes and their fields.

    Example GraphQL query structure:
    query CubeQuery {
      cube {
        cubeName {
          measureName
          dimensionName
          timeDimension {
            year
            month
          }
        }
      }
    }

    For example:
    query {
      cube {
        coursePerformanceSummary {
          average_course_gpa
          department_name
          semester_name
        }
      }
    }
    """

    cube_api_url: str = Field(default="http://cube_api:4000/cubejs-api/graphql")

    def _run(self, query: str) -> str:
        """Execute GraphQL query against Cube.js."""
        try:
            # Prepare GraphQL request
            payload = {
                "query": query
            }

            # Execute request
            response = requests.post(
                self.cube_api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            # Check for HTTP errors
            response.raise_for_status()

            # Parse response
            result = response.json()

            # Check for GraphQL errors
            if "errors" in result:
                errors = result["errors"]
                error_messages = [err.get("message", str(err)) for err in errors]
                return f"GraphQL Error: {'; '.join(error_messages)}"

            # Extract data
            if "data" not in result:
                return "No data returned from query"

            data = result["data"]

            # Format response
            if not data or "cube" not in data:
                return "Query executed but returned no results"

            cube_data = data["cube"]

            # Handle the response - cube is an array of objects
            if not isinstance(cube_data, list):
                return f"Unexpected response format: {cube_data}"

            if not cube_data:
                return "Query executed but returned no results"

            # Count total rows
            total_rows = len(cube_data)

            # Format output
            output = f"Query returned {total_rows} rows:\n\n"

            # Each item in the array has the cube name as a key
            for i, item in enumerate(cube_data[:20]):  # Limit to first 20 rows
                for cube_name, row_data in item.items():
                    output += f"Row {i + 1} ({cube_name}):\n"
                    if isinstance(row_data, dict):
                        for key, value in row_data.items():
                            output += f"  {key}: {value}\n"
                    else:
                        output += f"  {row_data}\n"
                    output += "\n"

            if total_rows > 20:
                output += f"... and {total_rows - 20} more rows\n"

            return output

        except requests.exceptions.RequestException as e:
            return f"Error connecting to Cube.js GraphQL API: {str(e)}"
        except Exception as e:
            return f"Error executing GraphQL query: {str(e)}"

    async def _arun(self, query: str) -> str:
        """Async version of _run."""
        return self._run(query)


def get_cube_graphql_tool() -> CubeGraphQLTool:
    """Factory function to create CubeGraphQLTool instance."""
    return CubeGraphQLTool()
