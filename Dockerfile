FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dbt-postgres with compatible protobuf
RUN pip install "protobuf>=4.0.0,<5.0.0" dbt-postgres==1.7.4

# Create working directory
WORKDIR /dbt

# Copy requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy dbt project files
COPY . .

# Set environment variables
ENV DBT_PROFILES_DIR=/dbt