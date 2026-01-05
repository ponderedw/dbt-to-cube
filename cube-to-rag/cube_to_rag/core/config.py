"""Configuration management for Cube.js RAG system."""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # LLM Configuration
    llm_model_id: str = os.getenv('LLM_MODEL_ID', 'anthropic:claude-3-5-sonnet-20241022')
    embedding_model: str = os.getenv('EMBEDDING_MODEL', 'openai:text-embedding-3-small')

    # API Keys
    anthropic_api_key: Optional[str] = os.getenv('ANTHROPIC_API_KEY')
    openai_api_key: Optional[str] = os.getenv('OPENAI_API_KEY')
    aws_access_key_id: Optional[str] = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key: Optional[str] = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_default_region: str = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')

    # Vector Database
    milvus_server_uri: str = os.getenv('MILVUS_SERVER_URI', 'http://milvus-standalone:19530')
    milvus_user: str = os.getenv('MILVUS_USER', 'root')
    milvus_password: Optional[str] = os.getenv('MILVUS_PASSWORD')

    # Cube.js API
    cube_url: str = os.getenv('CUBE_URL', 'http://cube_api:4000')
    cube_api_secret: Optional[str] = os.getenv('CUBEJS_API_SECRET')

    @property
    def cube_graphql_url(self) -> str:
        """Construct Cube.js GraphQL URL."""
        return f"{self.cube_url}/cubejs-api/graphql"

    @property
    def cube_api_url(self) -> str:
        """Construct Cube.js REST API URL."""
        return f"{self.cube_url}/cubejs-api/v1"

    @property
    def cube_api_token(self) -> Optional[str]:
        """Generate JWT token from Cube.js API secret."""
        if not self.cube_api_secret:
            return None

        try:
            import jwt
            import time

            payload = {
                "exp": int(time.time()) + (30 * 24 * 3600)  # 30 days
            }
            return jwt.encode(payload, self.cube_api_secret, algorithm="HS256")
        except ImportError:
            print("Warning: PyJWT not installed, cannot generate Cube.js token")
            return None

    # Cube.js SQL API
    cube_sql_host: str = os.getenv('CUBE_SQL_HOST', 'cube_api')
    cube_sql_port: int = int(os.getenv('CUBE_SQL_PORT', '15432'))
    cube_sql_database: str = os.getenv('CUBE_SQL_DATABASE', 'db')
    cube_sql_user: str = os.getenv('CUBE_SQL_USER', 'root')
    cube_sql_password: str = os.getenv('CUBE_SQL_PASSWORD', '')

    # Security
    secret_key: str = os.getenv('SECRET_KEY', 'change-me-in-production')
    fast_api_access_secret_token: str = os.getenv('FAST_API_ACCESS_SECRET_TOKEN', 'change-me-in-production')

    # Deployment
    deploy_env: str = os.getenv('DEPLOY_ENV', 'local')

    class Config:
        env_file = '.private.env'
        case_sensitive = False


settings = Settings()
