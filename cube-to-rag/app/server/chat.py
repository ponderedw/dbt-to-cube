"""Chat endpoints for conversational interface."""

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from typing import Dict, List

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools.retriever import create_retriever_tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from langchain_community.agent_toolkits.load_tools import load_tools

from cube_to_rag.core.llm import get_llm
from cube_to_rag.core.schema_embeddings import get_schema_embeddings
from cube_to_rag.models.chat import ChatMessage

chat_router = APIRouter()

# Store chat sessions (in production, use Redis or similar)
chat_sessions: Dict[str, List] = {}


@chat_router.post("/new")
async def new_chat_session(request: Request):
    """Initialize a new chat session."""
    session_id = request.session.get("session_id")
    if not session_id:
        # Generate new session ID
        import uuid
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id

    chat_sessions[session_id] = []
    return {"status": "success", "session_id": session_id}


@chat_router.post("/ask/")
async def ask_question(message: ChatMessage, request: Request):
    """
    Ask a question and stream the response.
    """
    session_id = request.session.get("session_id")
    if not session_id:
        return {"error": "No active session. Call /chat/new first."}

    # Get or initialize chat history
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []

    chat_history = chat_sessions[session_id]

    def safe_yield(content):
        """Ensure we only yield strings."""
        if isinstance(content, str):
            return content
        elif isinstance(content, (list, dict)):
            # Extract text from complex structures
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        text_parts.append(item['text'])
                    elif isinstance(item, str):
                        text_parts.append(item)
                return ''.join(text_parts) if text_parts else str(content)
            return str(content)
        else:
            return str(content)

    async def generate_response():
        """Generate streaming response."""
        try:
            # Initialize LLM and tools
            llm = get_llm()

            # Create retriever for cube schemas
            schema_embeddings = get_schema_embeddings()
            retriever = schema_embeddings.as_retriever(k=2)

            # Create retriever tool
            schema_search_tool = create_retriever_tool(
                retriever,
                "cube_schema_search",
                "Searches and retrieves Cube.js schema information including cube names, dimensions, and measures. "
                "Use this tool FIRST before querying data to discover what cubes, dimensions, and measures are available. "
                "Input should be a natural language description of the data you're looking for "
                "(e.g., 'course performance metrics', 'student enrollment data').",
                document_prompt=PromptTemplate(
                    template_format='jinja2',
                    input_variables=['cube_name', 'dimensions', 'measures', 'page_content'],
                    template='Cube: {{cube_name}}\n'
                             'Dimensions: {{dimensions}}\n'
                             'Measures: {{measures}}\n\n'
                             '{{page_content}}',
                ),
                document_separator='\n---\n',
            )

            # Load LangChain's built-in GraphQL tool
            graphql_tools = load_tools(
                ["graphql"],
                graphql_endpoint="http://cube_api:4000/cubejs-api/graphql",
                llm=llm
            )

            tools = [schema_search_tool] + graphql_tools

            # Create agent prompt
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are a helpful analytics assistant with access to Cube.js data via GraphQL.

IMPORTANT - Two-Step Process:
1. ALWAYS use the cube_schema_search tool FIRST to discover available cubes, dimensions, and measures
2. THEN use the cube_graphql_query tool to retrieve the actual data

Never guess or assume cube names, dimensions, or measures - always discover them first through search.

Workflow for answering questions:
1. Analyze the user's question to understand what data they need
2. Use cube_schema_search with a natural language description (e.g., "course performance metrics")
3. Review the search results to identify relevant cubes, dimensions, and measures
4. Construct a GraphQL query using the discovered schema information
5. Execute the query using cube_graphql_query
6. Explain the results in a clear, conversational way

GraphQL Query Format:
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

Always explain your reasoning and the data you found."""),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])

            # Create agent
            agent = create_tool_calling_agent(llm, tools, prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                handle_parsing_errors=True
            )

            # Execute agent with streaming
            final_output = ""

            async for event in agent_executor.astream_events(
                {"input": message.message, "chat_history": chat_history},
                version="v2"
            ):
                kind = event.get("event")

                # Stream LLM token by token
                if kind == "on_chat_model_stream":
                    content = event.get("data", {}).get("chunk", {})
                    if hasattr(content, "content"):
                        token = content.content
                        if token:
                            # Skip tool use chunks - only yield text content
                            if isinstance(token, list):
                                for item in token:
                                    if isinstance(item, dict) and item.get('type') == 'text':
                                        text = item.get('text', '')
                                        if text:
                                            final_output += text
                                            yield text
                            elif isinstance(token, str):
                                final_output += token
                                yield token

                # Capture final output if streaming didn't work
                elif kind == "on_chain_end" and event.get("name") == "AgentExecutor":
                    if not final_output:  # Only if we haven't streamed anything yet
                        output = event.get("data", {}).get("output", {})
                        output_text = safe_yield(output)
                        if output_text:
                            final_output = output_text
                            yield output_text

            # Update chat history
            if final_output:
                chat_history.append(HumanMessage(content=message.message))
                chat_history.append(AIMessage(content=final_output))
                chat_sessions[session_id] = chat_history

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            yield error_msg

    return StreamingResponse(generate_response(), media_type="text/plain")


@chat_router.get("/history")
async def get_chat_history(request: Request):
    """Get chat history for current session."""
    session_id = request.session.get("session_id")
    if not session_id or session_id not in chat_sessions:
        return {"history": []}

    history = chat_sessions[session_id]
    return {
        "history": [
            {
                "type": msg.__class__.__name__,
                "content": msg.content
            }
            for msg in history
        ]
    }


@chat_router.delete("/clear")
async def clear_chat_history(request: Request):
    """Clear chat history for current session."""
    session_id = request.session.get("session_id")
    if session_id and session_id in chat_sessions:
        chat_sessions[session_id] = []
    return {"status": "cleared"}
