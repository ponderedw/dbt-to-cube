#!/usr/bin/env bash

# Install dependencies
dbt deps --profiles-dir .

# Run dbt build first
echo "Running dbt build..."
dbt build --target container --profiles-dir .

if [ $? -eq 0 ]; then
    echo "dbt build completed successfully!"

    # Generate documentation
    echo "Generating dbt documentation..."
    dbt docs generate --target container --profiles-dir .

    # Serve documentation on port 80
    echo "Starting dbt docs server on port 80..."
    dbt docs serve --profiles-dir . --port 80
else
    echo "dbt build failed! Check the logs."
    exit 1
fi