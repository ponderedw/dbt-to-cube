import os

# Superset configuration file

# The SQLAlchemy connection string to your database backend
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://dbt_user:dbt_password@postgres:5432/superset_db"

# Flask App Builder configuration
# Your App secret key - change this in production
SECRET_KEY = 'your_secret_key_change_this_in_production'

# The authentication type
# AUTH_OID : Is for OpenID
# AUTH_DB : Is for database (username/password)
# AUTH_LDAP : Is for LDAP
# AUTH_REMOTE_USER : Is for using REMOTE_USER from web server
AUTH_TYPE = 1  # AUTH_DB

# Uncomment to setup Your App name
APP_NAME = "Education Analytics - Superset"

# Uncomment to setup an App icon
# APP_ICON = "/static/img/logo.png"

# Feature flags
FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    "ENABLE_TEMPLATE_PROCESSING": True,
}

# Cache configuration
CACHE_CONFIG = {
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300
}

# Enable CORS for development
ENABLE_CORS = True

# Default row limit for SQL Lab
DEFAULT_SQLLAB_LIMIT = 5000

# CSV export encoding
CSV_EXPORT = {
    'encoding': 'utf-8',
}

# Timeout for SQL Lab queries (in seconds)
SQLLAB_TIMEOUT = 300
SUPERSET_WEBSERVER_TIMEOUT = 300