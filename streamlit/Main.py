import streamlit as st
import os
import requests
import datetime
import dateutil.relativedelta


if "http_session" not in st.session_state:
    st.session_state.http_session = requests.Session()
    # Initialize session with FastAPI backend
    response = st.session_state.http_session.post(
        "http://fastapi:8080/chat/new",
        headers={"x-access-token": os.environ.get('FAST_API_ACCESS_SECRET_TOKEN')}
    )
    response.raise_for_status()


def get_chat_response(prompt):
    """Stream chat response from FastAPI backend."""
    url = "http://fastapi:8080/chat/ask/"
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


# Page configuration
st.set_page_config(
    page_title="Cube.js Analytics Chat",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Cube.js Analytics Chat")
st.markdown("Ask questions about your data and get insights from Cube.js!")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = [{
        "role": "assistant",
        "content": "Hello! 👋 I'm your Cube.js analytics assistant. Ask me anything about your course performance data!"
    }]

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
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

# Sidebar with information
with st.sidebar:
    st.header("About")
    st.markdown("""
    This chat interface allows you to:
    - Query Cube.js data using natural language
    - Get insights about course performance
    - Retrieve analytics using RAG (Retrieval-Augmented Generation)

    **Data Sources:**
    - Course Performance Summary
    - Cube.js Pre-aggregations
    - Vector-based semantic search
    """)

    if st.button("Clear Chat History"):
        st.session_state.messages = [{
            "role": "assistant",
            "content": "Chat history cleared! How can I help you?"
        }]
        st.rerun()
