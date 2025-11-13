FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dbt-postgres
RUN pip install --no-cache-dir \
    dbt-postgres==1.8.0 \
    dbt-core==1.8.0

# Set working directory
WORKDIR /usr/app/dbt/

# Copy dbt project files
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose port for dbt docs serve
EXPOSE 80

# Set entrypoint
ENTRYPOINT ["./entrypoint.sh"]