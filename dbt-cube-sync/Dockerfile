FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Set working directory
WORKDIR /app

# Copy Poetry configuration and README
COPY pyproject.toml poetry.lock* README.md ./

# Configure Poetry to not create virtual environment (since we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies only (no root package)
RUN poetry install --only main --no-root

# Copy application code
COPY dbt_cube_sync/ ./dbt_cube_sync/

# Install the application
RUN poetry install --only main

# Create a non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser
