#!/usr/bin/env bash

# Install dependencies
dbt deps --profiles-dir .

# Generate documentation
dbt docs generate --target container --profiles-dir .

# Serve documentation on port 80
dbt docs serve --profiles-dir . --port 80