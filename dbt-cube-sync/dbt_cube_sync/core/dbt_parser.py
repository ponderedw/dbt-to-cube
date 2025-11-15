"""
dbt manifest parser - extracts models, metrics, and column information
"""
import json
import os
from typing import Dict, List
from pathlib import Path

from .models import DbtModel, DbtColumn, DbtMetric


class DbtParser:
    """Parses dbt manifest.json to extract model and metric information"""
    
    def __init__(self, manifest_path: str, catalog_path: str = None):
        """
        Initialize the parser
        
        Args:
            manifest_path: Path to dbt manifest.json file
            catalog_path: Optional path to dbt catalog.json for column types
        """
        self.manifest_path = manifest_path
        self.catalog_path = catalog_path
        self.manifest = self._load_manifest()
        self.catalog = self._load_catalog() if catalog_path else None
    
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
            
            model = self._parse_model(node_id, node_data)
            if model and model.columns and model.metrics:  # Only include models with BOTH columns AND metrics
                models.append(model)
        
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
        
        return DbtModel(
            name=model_name,
            database=model_database,
            schema_name=model_schema,
            node_id=node_id,
            columns=columns,
            metrics=metrics
        )
    
    def _parse_columns(self, node_id: str, node_data: dict) -> Dict[str, DbtColumn]:
        """Parse columns for a model, enhanced with catalog data if available"""
        columns = {}
        manifest_columns = node_data.get('columns', {})
        
        # Get catalog columns for type information
        catalog_columns = {}
        if self.catalog and node_id in self.catalog.get('nodes', {}):
            catalog_columns = self.catalog['nodes'][node_id].get('columns', {})
        
        # If manifest has columns, use them with catalog type info
        if manifest_columns:
            for col_name, col_data in manifest_columns.items():
                data_type = None
                
                # Try to get data type from catalog
                if col_name in catalog_columns:
                    data_type = catalog_columns[col_name].get('type', '')
                
                columns[col_name] = DbtColumn(
                    name=col_name,
                    data_type=data_type,
                    description=col_data.get('description'),
                    meta=col_data.get('meta', {})
                )
        else:
            # If no manifest columns, use all catalog columns
            for col_name, col_data in catalog_columns.items():
                columns[col_name] = DbtColumn(
                    name=col_name,
                    data_type=col_data.get('type', ''),
                    description=f"Column from catalog: {col_name}",
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