import streamlit as st
import os
import requests
import datetime
import dateutil.relativedelta
import json
import re
import plotly.graph_objects as go
import plotly.express as px

# Page configuration MUST be first Streamlit command
st.set_page_config(
    page_title="Cube.js Analytics Chat",
    page_icon="chart_with_upwards_trend",
    layout="wide"
)


def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        expected_password = os.environ.get('STREAMLIT_PASSWORD', '')

        # If no password is set in environment, allow access
        if not expected_password:
            st.session_state["password_correct"] = True
            return

        # Hash the entered password for comparison
        entered_password = st.session_state["password"]

        if entered_password == expected_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Don't store password
        else:
            st.session_state["password_correct"] = False

    # Return True if password is already correct
    if st.session_state.get("password_correct", False):
        return True

    # Show input for password
    st.markdown("## Cube.js Analytics Chat - Login")
    st.markdown("Please enter the password to access the application.")

    st.text_input(
        "Password",
        type="password",
        on_change=password_entered,
        key="password",
    )

    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("Password incorrect")

    return False


# Check password before showing the app
if not check_password():
    st.stop()


# Get FastAPI URL from environment or use default
FASTAPI_URL = os.environ.get('FASTAPI_URL', 'http://fastapi:8080')

if not st.session_state.get("backend_ready"):
    _session = requests.Session()
    try:
        _resp = _session.post(
            f"{FASTAPI_URL}/chat/new",
            headers={"x-access-token": os.environ.get('FAST_API_ACCESS_SECRET_TOKEN')},
            timeout=10
        )
        _resp.raise_for_status()
        st.session_state.http_session = _session
        st.session_state.backend_ready = True
    except Exception as e:
        st.warning(f"API backend not ready yet ({FASTAPI_URL}). Retrying in 5 seconds…")
        st.markdown('<meta http-equiv="refresh" content="5">', unsafe_allow_html=True)
        st.stop()

if "contexts" not in st.session_state:
    st.session_state.contexts = []


def upload_context_to_backend(content: str, name: str):
    """Upload context to FastAPI backend."""
    url = f"{FASTAPI_URL}/chat/context"
    response = st.session_state.http_session.post(
        url,
        headers={"x-access-token": os.environ.get('FAST_API_ACCESS_SECRET_TOKEN')},
        data={"content": content, "name": name}
    )
    return response.json()


def clear_contexts_from_backend():
    """Clear all contexts from FastAPI backend."""
    url = f"{FASTAPI_URL}/chat/context"
    response = st.session_state.http_session.delete(
        url,
        headers={"x-access-token": os.environ.get('FAST_API_ACCESS_SECRET_TOKEN')}
    )
    return response.json()


def parse_chart_blocks(text: str):
    """
    Parse text for chart blocks and return list of content blocks.
    Chart blocks are in format: ```chart {...json...} ```
    """
    pattern = r'```chart\s*\n?(.*?)\n?```'
    blocks = []
    last_end = 0

    for match in re.finditer(pattern, text, re.DOTALL):
        # Add text before this chart
        if match.start() > last_end:
            text_before = text[last_end:match.start()].strip()
            if text_before:
                blocks.append({"type": "text", "content": text_before})

        # Parse the chart JSON
        try:
            chart_json = json.loads(match.group(1).strip())
            blocks.append({"type": "chart", "content": chart_json})
        except json.JSONDecodeError as e:
            # If JSON parsing fails, treat as text
            blocks.append({"type": "text", "content": f"```chart\n{match.group(1)}\n```"})

        last_end = match.end()

    # Add remaining text
    if last_end < len(text):
        remaining = text[last_end:].strip()
        if remaining:
            blocks.append({"type": "text", "content": remaining})

    # If no blocks found, return the whole text
    if not blocks:
        blocks.append({"type": "text", "content": text})

    return blocks


def render_chart(chart_data: dict):
    """Render a chart using Plotly based on chart specification."""
    chart_type = chart_data.get("type", "bar").lower()
    title = chart_data.get("title", "")
    data = chart_data.get("data", {})
    x_label = chart_data.get("x_label", "")
    y_label = chart_data.get("y_label", "")

    labels = data.get("labels", [])
    values = data.get("values", [])
    series = data.get("series", [])

    fig = None

    try:
        if chart_type == "pie":
            fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
            fig.update_layout(title=title)

        elif chart_type == "bar":
            if series:
                fig = go.Figure()
                for s in series:
                    fig.add_trace(go.Bar(name=s.get("name", ""), x=labels, y=s.get("values", [])))
                fig.update_layout(barmode='group')
            else:
                fig = go.Figure(data=[go.Bar(x=labels, y=values)])
            fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

        elif chart_type == "line":
            if series:
                fig = go.Figure()
                for s in series:
                    fig.add_trace(go.Scatter(name=s.get("name", ""), x=labels, y=s.get("values", []), mode='lines+markers'))
            else:
                fig = go.Figure(data=[go.Scatter(x=labels, y=values, mode='lines+markers')])
            fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

        elif chart_type == "area":
            if series:
                fig = go.Figure()
                for s in series:
                    fig.add_trace(go.Scatter(name=s.get("name", ""), x=labels, y=s.get("values", []), fill='tozeroy'))
            else:
                fig = go.Figure(data=[go.Scatter(x=labels, y=values, fill='tozeroy')])
            fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

        elif chart_type == "scatter":
            if series:
                fig = go.Figure()
                for s in series:
                    fig.add_trace(go.Scatter(name=s.get("name", ""), x=labels, y=s.get("values", []), mode='markers'))
            else:
                fig = go.Figure(data=[go.Scatter(x=labels, y=values, mode='markers')])
            fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

        else:
            # Default to bar chart
            fig = go.Figure(data=[go.Bar(x=labels, y=values)])
            fig.update_layout(title=title, xaxis_title=x_label, yaxis_title=y_label)

        if fig:
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Error rendering chart: {str(e)}")
        st.json(chart_data)


def render_response(response_text: str):
    """Parse and render the response with charts and text."""
    blocks = parse_chart_blocks(response_text)

    for block in blocks:
        if block["type"] == "text":
            st.markdown(block["content"])
        elif block["type"] == "chart":
            render_chart(block["content"])


def get_chat_response(prompt):
    """Stream chat response from FastAPI backend."""
    url = f"{FASTAPI_URL}/chat/ask/"
    start_time = datetime.datetime.now()
    with st.session_state.http_session.post(
            url,
            stream=True,
            headers={"x-access-token": os.environ.get('FAST_API_ACCESS_SECRET_TOKEN')},
            json={'message': prompt}
            ) as response:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                yield str(chunk, encoding="utf-8")
    rd = dateutil.relativedelta.relativedelta(datetime.datetime.now(), start_time)
    yield f"\n\n_Response time: {rd.minutes} minutes and {rd.seconds} seconds_"


st.title("Cube.js Analytics Chat")
st.markdown("Ask questions about your data and get insights from Cube.js!")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hello! I'm your Cube.js analytics assistant. Ask me anything about your data! You can also ask me to create charts and visualizations."
    }]

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            render_response(message["content"])
        else:
            st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask a question about your data..."):
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display assistant response
    with st.chat_message("assistant"):
        response = st.write_stream(get_chat_response(prompt))
    st.session_state.messages.append({"role": "assistant", "content": response})

    # Re-render the last message with proper chart parsing
    st.rerun()

# Sidebar with information and context upload
with st.sidebar:
    st.header("About")
    st.markdown("""
    This chat interface allows you to:
    - Query Cube.js data using natural language
    - Get insights about course performance
    - Generate charts and visualizations (pie, bar, line, area, scatter)
    - Retrieve analytics using RAG (Retrieval-Augmented Generation)

    **Data Sources:**
    - Course Performance Summary
    - Cube.js Pre-aggregations
    - Vector-based semantic search
    """)

    st.divider()

    # Context upload section
    st.header("Context Files")
    st.markdown("Upload files or text to keep in context for all conversations.")

    # Display current contexts
    if st.session_state.contexts:
        st.markdown("**Uploaded Contexts:**")
        for ctx in st.session_state.contexts:
            st.markdown(f"- {ctx}")

    # File upload
    context_file = st.file_uploader(
        "Upload context file",
        type=['txt', 'md', 'json', 'csv', 'yaml', 'yml'],
        help="Upload a file to add to the conversation context"
    )

    if context_file is not None:
        if st.button("Add File to Context"):
            try:
                content = context_file.read().decode("utf-8")
                result = upload_context_to_backend(content, context_file.name)
                if result.get("status") == "success":
                    st.session_state.contexts.append(context_file.name)
                    st.success(f"Added '{context_file.name}' to context")
                    st.rerun()
                else:
                    st.error(result.get("error", "Failed to add context"))
            except Exception as e:
                st.error(f"Error: {str(e)}")

    # Text input for context
    with st.expander("Add text context"):
        context_name = st.text_input("Context name", placeholder="e.g., business_rules")
        context_text = st.text_area("Context content", placeholder="Enter any text to keep in context...")
        if st.button("Add Text to Context"):
            if context_text and context_name:
                result = upload_context_to_backend(context_text, context_name)
                if result.get("status") == "success":
                    st.session_state.contexts.append(context_name)
                    st.success(f"Added '{context_name}' to context")
                    st.rerun()
                else:
                    st.error(result.get("error", "Failed to add context"))
            else:
                st.warning("Please provide both name and content")

    if st.session_state.contexts:
        if st.button("Clear All Contexts"):
            clear_contexts_from_backend()
            st.session_state.contexts = []
            st.success("Contexts cleared")
            st.rerun()

    st.divider()

    if st.button("Clear Chat History"):
        st.session_state.messages = [{
            "role": "assistant",
            "content": "Chat history cleared! How can I help you?"
        }]
        st.rerun()
