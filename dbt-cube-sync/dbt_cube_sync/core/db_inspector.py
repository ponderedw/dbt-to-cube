"""
Database inspector - fetches column types using SQLAlchemy or direct SQL.

Uses Redshift-specific queries for Redshift databases (which don't support
standard PostgreSQL reflection), and SQLAlchemy reflection for other databases.
"""
from typing import Dict, Optional
from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.engine import Engine


class DatabaseInspector:
    """Inspects database schema to extract column type information."""

    def __init__(self, sqlalchemy_uri: str):
        """
        Initialize the database inspector.

        Args:
            sqlalchemy_uri: SQLAlchemy connection URI (e.g., postgresql://user:pass@host:port/db)
        """
        self.is_redshift = 'redshift' in sqlalchemy_uri.lower()

        if self.is_redshift:
            self.engine: Engine = create_engine(
                sqlalchemy_uri,
                connect_args={'sslmode': 'prefer'}
            )
        else:
            self.engine: Engine = create_engine(sqlalchemy_uri)

        self.metadata = MetaData()
        self._table_cache: Dict[str, Dict[str, str]] = {}

    def _get_redshift_columns(self, schema: str, table_name: str) -> Dict[str, str]:
        """
        Get column types from Redshift using LIMIT 0 query (fastest method).

        Executes SELECT * FROM table LIMIT 0 and reads column types from cursor description.
        This is very fast because it doesn't scan any data - just returns metadata.
        """
        columns = {}

        # LIMIT 0 query - returns no rows but gives us column metadata
        query = text(f'SELECT * FROM "{schema}"."{table_name}" LIMIT 0')

        # Redshift type OID to name mapping (common types)
        redshift_type_map = {
            16: 'boolean',
            20: 'bigint',
            21: 'smallint',
            23: 'integer',
            25: 'text',
            700: 'real',
            701: 'double precision',
            1042: 'char',
            1043: 'varchar',
            1082: 'date',
            1083: 'time',
            1114: 'timestamp',
            1184: 'timestamptz',
            1700: 'numeric',
            2950: 'uuid',
        }

        try:
            with self.engine.connect() as conn:
                result = conn.execute(query)
                # Get column info from cursor description
                # Format: (name, type_code, display_size, internal_size, precision, scale, null_ok)
                if result.cursor and result.cursor.description:
                    for col_desc in result.cursor.description:
                        col_name = col_desc[0]
                        type_code = col_desc[1]
                        # Map type code to type name, fallback to 'varchar' if unknown
                        col_type = redshift_type_map.get(type_code, 'varchar')
                        columns[col_name] = col_type

        except Exception as e:
            print(f"Warning: Could not inspect Redshift table {schema}.{table_name}: {e}")

        return columns

    def get_table_columns(self, schema: str, table_name: str) -> Dict[str, str]:
        """
        Get column names and their data types for a specific table.

        Uses Redshift-specific queries for Redshift, SQLAlchemy reflection for others.

        Args:
            schema: Database schema name
            table_name: Table name

        Returns:
            Dictionary mapping column names to data types
        """
        cache_key = f"{schema}.{table_name}"

        # Check cache first
        if cache_key in self._table_cache:
            return self._table_cache[cache_key]

        columns = {}

        if self.is_redshift:
            # Use Redshift-specific query
            columns = self._get_redshift_columns(schema, table_name)
        else:
            # Use standard SQLAlchemy reflection
            try:
                table = Table(
                    table_name,
                    self.metadata,
                    autoload_with=self.engine,
                    schema=schema
                )
                for column in table.columns:
                    columns[column.name] = str(column.type)

            except Exception as e:
                print(f"Warning: Could not inspect table {schema}.{table_name}: {e}")

        self._table_cache[cache_key] = columns
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
