"""
Database inspector - fetches column types using SQLAlchemy MetaData reflection.

Uses SQLAlchemy's Table(..., autoload_with=engine) for portable, database-agnostic
column type extraction. This approach works consistently across PostgreSQL, MySQL,
Snowflake, BigQuery, Redshift, and other databases.
"""
from typing import Dict, Optional
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.engine import Engine


class DatabaseInspector:
    """Inspects database schema to extract column type information using SQLAlchemy reflection."""

    def __init__(self, sqlalchemy_uri: str):
        """
        Initialize the database inspector.

        Args:
            sqlalchemy_uri: SQLAlchemy connection URI (e.g., postgresql://user:pass@host:port/db)
        """
        # Add connect_args for Redshift compatibility
        if 'redshift' in sqlalchemy_uri.lower():
            self.engine: Engine = create_engine(
                sqlalchemy_uri,
                connect_args={'sslmode': 'prefer'}
            )
        else:
            self.engine: Engine = create_engine(sqlalchemy_uri)

        self.metadata = MetaData()
        self._table_cache: Dict[str, Table] = {}

    def get_table_columns(self, schema: str, table_name: str) -> Dict[str, str]:
        """
        Get column names and their data types for a specific table.

        Uses SQLAlchemy MetaData reflection for portable column extraction.

        Args:
            schema: Database schema name
            table_name: Table name

        Returns:
            Dictionary mapping column names to data types
        """
        columns = {}
        cache_key = f"{schema}.{table_name}"

        try:
            # Check cache first
            if cache_key in self._table_cache:
                table = self._table_cache[cache_key]
            else:
                # Reflect table using SQLAlchemy MetaData
                table = Table(
                    table_name,
                    self.metadata,
                    autoload_with=self.engine,
                    schema=schema
                )
                self._table_cache[cache_key] = table

            # Extract column types
            for column in table.columns:
                columns[column.name] = str(column.type)

        except Exception as e:
            print(f"Warning: Could not inspect table {schema}.{table_name}: {e}")

        return columns

    def reflect_multiple_tables(
        self, tables: list[tuple[str, str]]
    ) -> Dict[str, Dict[str, str]]:
        """
        Reflect multiple tables in bulk for performance optimization.

        Args:
            tables: List of (schema, table_name) tuples

        Returns:
            Dict mapping "schema.table_name" -> {column_name: column_type}
        """
        results = {}

        for schema, table_name in tables:
            cache_key = f"{schema}.{table_name}"
            results[cache_key] = self.get_table_columns(schema, table_name)

        return results

    def close(self):
        """Close the database connection and clear cache."""
        self._table_cache.clear()
        self.engine.dispose()
