"""
Database inspector - fetches column types using SQLAlchemy
"""
from typing import Dict, Optional
from sqlalchemy import create_engine, inspect, MetaData, Table
from sqlalchemy.engine import Engine


class DatabaseInspector:
    """Inspects database schema to extract column type information"""

    def __init__(self, sqlalchemy_uri: str):
        """
        Initialize the database inspector

        Args:
            sqlalchemy_uri: SQLAlchemy connection URI (e.g., postgresql://user:pass@host:port/db)
        """
        self.engine: Engine = create_engine(sqlalchemy_uri)
        self.inspector = inspect(self.engine)

    def get_table_columns(self, schema: str, table_name: str) -> Dict[str, str]:
        """
        Get column names and their data types for a specific table

        Args:
            schema: Database schema name
            table_name: Table name

        Returns:
            Dictionary mapping column names to data types
        """
        columns = {}

        try:
            # Get columns from the database
            table_columns = self.inspector.get_columns(table_name, schema=schema)

            for column in table_columns:
                col_name = column['name']
                col_type = str(column['type'])
                columns[col_name] = col_type

        except Exception as e:
            print(f"Warning: Could not inspect table {schema}.{table_name}: {e}")

        return columns

    def close(self):
        """Close the database connection"""
        self.engine.dispose()
