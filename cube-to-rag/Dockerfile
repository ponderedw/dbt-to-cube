FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Configure Poetry: Don't create virtual env (we're in Docker)
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /code

# Copy dependency files and README
COPY pyproject.toml README.md /code/

# Copy package code (needed for Poetry install)
COPY cube_to_rag /code/cube_to_rag

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi \
    && rm -rf /tmp/poetry_cache

# Copy application code
COPY app /code/app

ENV PYTHONPATH="${PYTHONPATH}:/code:/code/app"

# Run FastAPI using uvicorn
CMD ["uvicorn", "app.server.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
