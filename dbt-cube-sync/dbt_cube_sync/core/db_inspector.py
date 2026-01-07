"""
Database inspector - fetches column types using SQLAlchemy
"""
from typing import Dict, Optional
from sqlalchemy import create_engine, inspect, MetaData, Table, text
from sqlalchemy.engine import Engine


class DatabaseInspector:
    """Inspects database schema to extract column type information"""

    def __init__(self, sqlalchemy_uri: str):
        """
        Initialize the database inspector

        Args:
            sqlalchemy_uri: SQLAlchemy connection URI (e.g., postgresql://user:pass@host:port/db)
        """
        # Add connect_args for Redshift compatibility
        if 'redshift' in sqlalchemy_uri:
            self.engine: Engine = create_engine(
                sqlalchemy_uri,
                connect_args={'sslmode': 'prefer'}
            )
        else:
            self.engine: Engine = create_engine(sqlalchemy_uri)

        self.inspector = inspect(self.engine)
        self.is_redshift = 'redshift' in sqlalchemy_uri.lower()

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
            # For Redshift, use direct SQL query to avoid pg_catalog issues
            if self.is_redshift:
                columns = self._get_redshift_columns(schema, table_name)
            else:
                # Get columns from the database using inspector
                table_columns = self.inspector.get_columns(table_name, schema=schema)

                for column in table_columns:
                    col_name = column['name']
                    col_type = str(column['type'])
                    columns[col_name] = col_type

        except Exception as e:
            print(f"Warning: Could not inspect table {schema}.{table_name}: {e}")

        return columns

    def _get_redshift_columns(self, schema: str, table_name: str) -> Dict[str, str]:
        """
        Get columns for Redshift using direct SQL query

        Args:
            schema: Database schema name
            table_name: Table name

        Returns:
            Dictionary mapping column names to data types
        """
        columns = {}

        try:
            # Query Redshift's pg_table_def view which is more reliable
            query = text("""
                SELECT column_name, data_type
                FROM pg_table_def
                WHERE schemaname = :schema
                AND tablename = :table_name
                ORDER BY column_name
            """)

            with self.engine.connect() as conn:
                result = conn.execute(query, {"schema": schema, "table_name": table_name})
                for row in result:
                    columns[row[0]] = row[1]

        except Exception as e:
            # Fallback to information_schema if pg_table_def fails
            try:
                query = text("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = :schema
                    AND table_name = :table_name
                    ORDER BY ordinal_position
                """)

                with self.engine.connect() as conn:
                    result = conn.execute(query, {"schema": schema, "table_name": table_name})
                    for row in result:
                        columns[row[0]] = row[1]
            except Exception as fallback_error:
                print(f"Warning: Could not query Redshift table {schema}.{table_name}: {fallback_error}")

        return columns

    def close(self):
        """Close the database connection"""
        self.engine.dispose()
