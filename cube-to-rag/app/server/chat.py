"""Chat endpoints for conversational interface."""

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from typing import Dict, List, Optional
import io

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage

from cube_to_rag.core.llm import get_llm
from cube_to_rag.core.config import settings
from cube_to_rag.models.chat import ChatMessage, ContextUpload
from cube_to_rag.tools import get_cube_schema_search_tool, get_cube_graphql_tools, CUBE_GRAPHQL_INSTRUCTIONS

chat_router = APIRouter()

# Store chat sessions (in production, use Redis or similar)
chat_sessions: Dict[str, List] = {}

# Store session contexts (persistent context for each session)
session_contexts: Dict[str, List[dict]] = {}


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
    session_contexts[session_id] = []
    return {"status": "success", "session_id": session_id}


@chat_router.post("/context")
async def upload_context(
    request: Request,
    context_file: Optional[UploadFile] = File(None),
    content: Optional[str] = Form(None),
    name: Optional[str] = Form(None)
):
    """
    Upload context that will be stored and used for all future messages in this session.
    Can accept either a file upload or direct text content.
    """
    session_id = request.session.get("session_id")
    if not session_id:
        return {"error": "No active session. Call /chat/new first."}

    if session_id not in session_contexts:
        session_contexts[session_id] = []

    context_content = ""
    context_name = name or "uploaded_context"

    if context_file:
        # Read file content
        file_content = await context_file.read()
        try:
            context_content = file_content.decode("utf-8")
        except UnicodeDecodeError:
            # Try other encodings
            try:
                context_content = file_content.decode("latin-1")
            except:
                return {"error": "Could not decode file content"}
        context_name = name or context_file.filename or "uploaded_file"
    elif content:
        context_content = content
    else:
        return {"error": "No content provided. Send either 'context_file' or 'content'."}

    # Store the context
    session_contexts[session_id].append({
        "name": context_name,
        "content": context_content
    })

    return {
        "status": "success",
        "message": f"Context '{context_name}' added to session",
        "total_contexts": len(session_contexts[session_id])
    }


@chat_router.get("/context")
async def get_contexts(request: Request):
    """Get all stored contexts for current session."""
    session_id = request.session.get("session_id")
    if not session_id or session_id not in session_contexts:
        return {"contexts": []}

    return {
        "contexts": [
            {"name": ctx["name"], "length": len(ctx["content"])}
            for ctx in session_contexts[session_id]
        ]
    }


@chat_router.delete("/context")
async def clear_contexts(request: Request):
    """Clear all stored contexts for current session."""
    session_id = request.session.get("session_id")
    if session_id and session_id in session_contexts:
        session_contexts[session_id] = []
    return {"status": "cleared"}


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

    # Get stored contexts for this session
    contexts = session_contexts.get(session_id, [])

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

            # Create Cube.js tools
            schema_search_tool = get_cube_schema_search_tool(k=5)
            graphql_tools = get_cube_graphql_tools(
                graphql_endpoint=settings.cube_graphql_url,
                llm=llm,
                api_token=settings.cube_api_token,
                max_retries=settings.cube_graphql_max_retries,
                retry_delay=settings.cube_graphql_retry_delay
            )

            tools = [schema_search_tool] + graphql_tools

            # Build context section if any contexts exist
            context_section = ""
            if contexts:
                context_section = "📚 STORED CONTEXT (use this information in your responses):\n"
                context_section += "=" * 50 + "\n"
                for ctx in contexts:
                    context_section += f"\n### {ctx['name']}:\n{ctx['content']}\n"
                context_section += "=" * 50 + "\n\n"

            # Create agent prompt
            system_message = f'''You are a helpful analytics assistant with access to Cube.js data.

{context_section}✨ IMPORTANT NOTES:
- The cube_graphql_query tool has built-in retry logic for pre-aggregation delays
- If you see a message about 'pre-aggregations building', the tool is handling it automatically
- Just wait for the tool to complete - it will retry automatically

📊 VISUALIZATION CAPABILITIES:
When the user asks for charts, graphs, or visualizations, you can generate them using special code blocks.
Supported chart types: pie, bar, line, area, scatter

To create a chart, use this format:
```chart
{{{{"type": "pie|bar|line|area|scatter", "title": "Chart Title", "data": {{{{"labels": ["A", "B", "C"], "values": [10, 20, 30]}}}}, "x_label": "X Axis", "y_label": "Y Axis"}}}}
```

For multi-series charts (line, bar, area):
```chart
{{{{"type": "line", "title": "Trend", "data": {{{{"labels": ["Jan", "Feb"], "series": [{{{{"name": "Sales", "values": [100, 150]}}}}, {{{{"name": "Costs", "values": [80, 90]}}}}]}}}}}}}}
```

You can also return data tables in markdown format.

{CUBE_GRAPHQL_INSTRUCTIONS}

🎯 Your job is to:
- Search for relevant schemas using cube_schema_search
- Pass the discovered cube/dimension/measure names to cube_graphql_query
- Explain the results clearly
- When asked for visualizations, generate appropriate charts using the chart code block format

Always explain your reasoning and findings.'''

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_message),
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
