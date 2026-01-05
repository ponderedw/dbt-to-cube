FROM python:3.12-slim

WORKDIR /app

COPY streamlit/requirements.txt ./streamlit/requirements.txt

RUN pip install --no-cache-dir -r streamlit/requirements.txt

COPY streamlit ./streamlit

EXPOSE 8501

CMD ["streamlit", "run", "streamlit/Main.py", "--server.port=8501", "--server.address=0.0.0.0"]
