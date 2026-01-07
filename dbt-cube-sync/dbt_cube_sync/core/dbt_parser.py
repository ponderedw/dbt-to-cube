"""
dbt manifest parser - extracts models, metrics, and column information
"""
import json
import os
from typing import Dict, List, Optional
from pathlib import Path

from .models import DbtModel, DbtColumn, DbtMetric, DbtPreAggregation, DbtRefreshKey
from .db_inspector import DatabaseInspector


class DbtParser:
    """Parses dbt manifest.json to extract model and metric information"""

    def __init__(
        self,
        manifest_path: str,
        catalog_path: Optional[str] = None,
        sqlalchemy_uri: Optional[str] = None,
        model_filter: Optional[List[str]] = None
    ):
        """
        Initialize the parser

        Args:
            manifest_path: Path to dbt manifest.json file
            catalog_path: Optional path to dbt catalog.json for column types
            sqlalchemy_uri: Optional SQLAlchemy URI to connect to database for column types
            model_filter: Optional list of model names to process (if None, processes all models)
        """
        self.manifest_path = manifest_path
        self.catalog_path = catalog_path
        self.sqlalchemy_uri = sqlalchemy_uri
        self.model_filter = model_filter
        self.manifest = self._load_manifest()
        self.catalog = self._load_catalog() if catalog_path else None
        self.db_inspector = DatabaseInspector(sqlalchemy_uri) if sqlalchemy_uri else None
    
    def _load_manifest(self) -> dict:
        """Load the dbt manifest.json file"""
        if not os.path.exists(self.manifest_path):
            raise FileNotFoundError(f"Manifest file not found: {self.manifest_path}")
        
        with open(self.manifest_path, 'r') as f:
            return json.load(f)
    
    def _load_catalog(self) -> dict:
        """Load the dbt catalog.json file if available"""
        if not self.catalog_path or not os.path.exists(self.catalog_path):
            return None
        
        try:
            with open(self.catalog_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load catalog file {self.catalog_path}: {e}")
            return None
    
    def parse_models(self) -> List[DbtModel]:
        """
        Extract models with metrics and columns from manifest

        Returns:
            List of DbtModel instances
        """
        models = []
        nodes = self.manifest.get('nodes', {})

        for node_id, node_data in nodes.items():
            # Only process models
            if node_data.get('resource_type') != 'model':
                continue

            # Apply model filter if specified
            model_name = node_data.get('name', '')
            if self.model_filter and model_name not in self.model_filter:
                continue

            model = self._parse_model(node_id, node_data)
            # Include models that have columns AND metrics (measures are required for useful Cube.js schemas)
            if model and model.columns and model.metrics:
                models.append(model)

        # Close database inspector if it was used
        if self.db_inspector:
            self.db_inspector.close()

        return models
    
    def _parse_model(self, node_id: str, node_data: dict) -> DbtModel:
        """Parse a single model from the manifest"""
        model_name = node_data.get('name', '')
        model_schema = node_data.get('schema', '')
        model_database = node_data.get('database', '')
        
        # Parse columns
        columns = self._parse_columns(node_id, node_data)
        
        # Parse metrics from config.meta.metrics
        metrics = self._parse_metrics(node_data)
        
        # Parse pre-aggregations from config.meta.pre_aggregations
        pre_aggregations = self._parse_pre_aggregations(node_data)
        
        return DbtModel(
            name=model_name,
            database=model_database,
            schema_name=model_schema,
            node_id=node_id,
            columns=columns,
            metrics=metrics,
            pre_aggregations=pre_aggregations
        )
    
    def _parse_columns(self, node_id: str, node_data: dict) -> Dict[str, DbtColumn]:
        """Parse columns for a model, enhanced with catalog or database data if available"""
        columns = {}
        manifest_columns = node_data.get('columns', {})

        # Get catalog columns for type information (if catalog is available)
        catalog_columns = {}
        if self.catalog and node_id in self.catalog.get('nodes', {}):
            catalog_columns = self.catalog['nodes'][node_id].get('columns', {})

        # Get database columns for type information (if db_inspector is available)
        db_columns = {}
        if self.db_inspector and not self.catalog:
            schema = node_data.get('schema', '')
            table_name = node_data.get('name', '')
            if schema and table_name:
                db_columns = self.db_inspector.get_table_columns(schema, table_name)

        # If manifest has columns, use them with catalog or database type info
        if manifest_columns:
            for col_name, col_data in manifest_columns.items():
                data_type = None

                # Try to get data type from catalog first
                if col_name in catalog_columns:
                    data_type = catalog_columns[col_name].get('type', '')
                # Otherwise try database
                elif col_name in db_columns:
                    data_type = db_columns[col_name]

                columns[col_name] = DbtColumn(
                    name=col_name,
                    data_type=data_type,
                    description=col_data.get('description'),
                    meta=col_data.get('meta', {})
                )
        else:
            # If no manifest columns, use catalog or database columns
            source_columns = catalog_columns or db_columns
            for col_name in source_columns:
                if catalog_columns:
                    col_data = catalog_columns[col_name]
                    data_type = col_data.get('type', '')
                    description = f"Column from catalog: {col_name}"
                else:
                    data_type = db_columns[col_name]
                    description = f"Column from database: {col_name}"

                columns[col_name] = DbtColumn(
                    name=col_name,
                    data_type=data_type,
                    description=description,
                    meta={}
                )

        return columns
    
    def _parse_metrics(self, node_data: dict) -> Dict[str, DbtMetric]:
        """Parse metrics from model configuration"""
        metrics = {}
        
        # Look for metrics in config.meta.metrics
        config = node_data.get('config', {})
        meta = config.get('meta', {})
        metrics_data = meta.get('metrics', {})
        
        for metric_name, metric_config in metrics_data.items():
            if isinstance(metric_config, dict):
                metrics[metric_name] = DbtMetric(
                    name=metric_name,
                    type=metric_config.get('type', 'sum'),
                    sql=metric_config.get('sql'),
                    title=metric_config.get('title', metric_name.replace('_', ' ').title()),
                    description=metric_config.get('description', metric_name.replace('_', ' ').title())
                )
        
        return metrics
    
    def _parse_pre_aggregations(self, node_data: dict) -> Dict[str, DbtPreAggregation]:
        """Parse pre-aggregations from model configuration"""
        pre_aggregations = {}
        
        # Look for pre-aggregations in config.meta.pre_aggregations
        config = node_data.get('config', {})
        meta = config.get('meta', {})
        pre_aggs_data = meta.get('pre_aggregations', {})
        
        for pre_agg_name, pre_agg_config in pre_aggs_data.items():
            if isinstance(pre_agg_config, dict):
                # Parse refresh_key if present
                refresh_key = None
                refresh_key_config = pre_agg_config.get('refresh_key')
                if refresh_key_config and isinstance(refresh_key_config, dict):
                    refresh_key = DbtRefreshKey(
                        every=refresh_key_config.get('every'),
                        sql=refresh_key_config.get('sql'),
                        incremental=refresh_key_config.get('incremental'),
                        update_window=refresh_key_config.get('update_window')
                    )
                
                pre_aggregations[pre_agg_name] = DbtPreAggregation(
                    name=pre_agg_name,
                    type=pre_agg_config.get('type', 'rollup'),
                    measures=pre_agg_config.get('measures', []),
                    dimensions=pre_agg_config.get('dimensions', []),
                    time_dimension=pre_agg_config.get('time_dimension'),
                    granularity=pre_agg_config.get('granularity'),
                    refresh_key=refresh_key
                )
        
        return pre_aggregations
    
    @staticmethod
    def map_dbt_type_to_cube_type(dbt_type: str) -> str:
        """Map dbt metric types to Cube.js measure types"""
        type_mapping = {
            'sum': 'sum',
            'average': 'avg',
            'avg': 'avg',
            'count': 'count',
            'count_distinct': 'countDistinct',
            'min': 'min',
            'max': 'max',
            'number': 'number',
        }
        return type_mapping.get(dbt_type.lower(), 'sum')
    
    @staticmethod
    def map_data_type_to_cube_type(data_type: str) -> str:
        """Map SQL/dbt data types to Cube.js dimension types"""
        if not data_type:
            return 'string'
        
        data_type = data_type.lower()
        
        if any(t in data_type for t in ['int', 'bigint', 'decimal', 'numeric', 'float', 'double']):
            return 'number'
        elif any(t in data_type for t in ['timestamp', 'datetime', 'date']):
            return 'time'
        elif any(t in data_type for t in ['bool']):
            return 'boolean'
        else:
            return 'string'