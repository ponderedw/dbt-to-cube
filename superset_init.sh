#!/bin/bash

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h postgres -p 5432 -U dbt_user; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 1
done
echo "PostgreSQL is ready!"

# Create superset database if it doesn't exist
echo "Creating superset database if it doesn't exist..."
PGPASSWORD=dbt_password psql -h postgres -U dbt_user -d education_dw -c "SELECT 1 FROM pg_database WHERE datname = 'superset_db';" | grep -q 1 || PGPASSWORD=dbt_password psql -h postgres -U dbt_user -d education_dw -c "CREATE DATABASE superset_db;"

# Grant permissions
echo "Granting permissions..."
PGPASSWORD=dbt_password psql -h postgres -U dbt_user -d superset_db -c "
GRANT ALL PRIVILEGES ON SCHEMA public TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO dbt_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO dbt_user;
"

# Initialize Superset database
echo "Initializing Superset database..."
superset db upgrade

# Create admin user
echo "Creating admin user..."
superset fab create-admin \
    --username admin \
    --firstname Admin \
    --lastname User \
    --email admin@superset.com \
    --password admin

# Load examples (optional - comment out if not needed)
# echo "Loading examples..."
# superset load_examples

# Initialize roles and permissions
echo "Initializing roles and permissions..."
superset init

echo "Superset initialization complete!"

# Start the Superset web server
echo "Starting Superset web server..."
superset run -p 8088 --host 0.0.0.0