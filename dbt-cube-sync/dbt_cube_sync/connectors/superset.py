"""
Superset connector for syncing Cube.js schemas
"""
import os
import re
import json
import requests
import time
from typing import Dict, List, Any, Optional
from pathlib import Path

from .base import BaseConnector, ConnectorRegistry
from ..core.models import SyncResult


class SupersetConnector(BaseConnector):
    """Connector for Apache Superset BI tool"""
    
    def __init__(self, url: str, username: str, password: str, database_name: str = "Cube", **kwargs):
        """
        Initialize Superset connector
        
        Args:
            url: Superset base URL (e.g., 'http://localhost:8088')
            username: Superset username
            password: Superset password
            database_name: Name of the database in Superset (default: "Cube")
        """
        super().__init__(
            url=url,
            username=username,
            password=password,
            database_name=database_name,
            **kwargs
        )
        
        self.base_url = url.rstrip('/')
        self.session = requests.Session()
        self.access_token = None
        self.csrf_token = None
        self.database_id = None
        
        self.connect()
    
    def _validate_config(self) -> None:
        """Validate the provided configuration"""
        required_fields = ['url', 'username', 'password']
        missing_fields = [field for field in required_fields if not self.config.get(field)]
        
        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {missing_fields}")
    
    def connect(self) -> None:
        """Establish connection to Superset"""
        self._login()
        self._get_csrf_token()
        self._get_database_id()
    
    def _login(self):
        """Authenticate and get JWT token"""
        login_url = f"{self.base_url}/api/v1/security/login"
        payload = {
            "username": self.config['username'],
            "password": self.config['password'],
            "provider": "db",
            "refresh": True
        }
        
        response = self.session.post(login_url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        self.access_token = data.get('access_token')
        
        # Set authorization header for all future requests
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        })
        
        print("✓ Successfully logged in to Superset")
    
    def _get_csrf_token(self):
        """Get CSRF token for POST requests"""
        csrf_url = f"{self.base_url}/api/v1/security/csrf_token/"
        response = self.session.get(csrf_url)
        response.raise_for_status()
        
        self.csrf_token = response.json().get('result')
        self.session.headers.update({'X-CSRFToken': self.csrf_token})
        
        print("✓ Retrieved CSRF token")
    
    def _get_database_id(self):
        """Get database ID by name"""
        database_name = self.config.get('database_name', 'Cube')
        databases_url = f"{self.base_url}/api/v1/database/"
        params = {
            "q": json.dumps({
                "filters": [
                    {
                        "col": "database_name",
                        "opr": "eq",
                        "value": database_name
                    }
                ]
            })
        }
        
        response = self.session.get(databases_url, params=params)
        response.raise_for_status()
        
        result = response.json().get('result', [])
        if not result:
            raise ValueError(f"Database '{database_name}' not found")
        
        self.database_id = result[0]['id']
        print(f"✓ Found database '{database_name}' with ID: {self.database_id}")
    
    def sync_cube_schemas(self, cube_dir: str) -> List[SyncResult]:
        """Sync all Cube.js schemas from directory to Superset"""
        results = []
        cube_files = self._get_cube_files(cube_dir)
        
        if not cube_files:
            return [SyncResult(
                file_or_dataset="No files",
                status="failed", 
                message=f"No .js files found in {cube_dir}"
            )]
        
        print(f"🔍 Found {len(cube_files)} Cube.js files")
        
        for cube_file in cube_files:
            try:
                print(f"\\n{'='*60}")
                print(f"Processing: {cube_file.name}")
                print(f"{'='*60}")
                
                result = self.sync_single_schema(str(cube_file))
                results.append(result)
                
            except Exception as e:
                print(f"✗ Error processing {cube_file.name}: {str(e)}")
                results.append(SyncResult(
                    file_or_dataset=cube_file.name,
                    status="failed",
                    error=str(e)
                ))
        
        # Print summary
        successful = sum(1 for r in results if r.status == 'success')
        failed = sum(1 for r in results if r.status == 'failed')
        print(f"\\n{'='*60}")
        print("SYNC SUMMARY")
        print(f"{'='*60}")
        print(f"✓ Successful: {successful}")
        print(f"✗ Failed: {failed}")
        print(f"Total: {len(results)}")
        
        return results
    
    def sync_single_schema(self, cube_file_path: str) -> SyncResult:
        """Sync a single Cube.js schema file to Superset"""
        try:
            schema_info = self._parse_cube_file(cube_file_path)
            dataset_id = self._create_or_update_dataset(schema_info)
            
            return SyncResult(
                file_or_dataset=Path(cube_file_path).name,
                status="success",
                message=f"Dataset created/updated with ID: {dataset_id}"
            )
            
        except Exception as e:
            return SyncResult(
                file_or_dataset=Path(cube_file_path).name,
                status="failed",
                error=str(e)
            )
    
    def _parse_cube_file(self, file_path: str) -> Dict[str, Any]:
        """Parse Cube.js schema file and extract metadata"""
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Extract cube name
        cube_name_match = re.search(r'cube\s*\(\s*[`"\']([^`"\']+)[`"\']', content)
        if not cube_name_match:
            raise ValueError(f"Could not find cube name in {file_path}")
        
        cube_name = cube_name_match.group(1)
        
        print(f"  Cube: {cube_name}")
        
        # Parse dimensions
        dimensions = self._parse_dimensions(content)
        
        # Parse measures
        measures = self._parse_measures(content)
        
        return {
            'cube_name': cube_name,
            'schema': 'public',             # Always use public schema for Cube.js
            'table_name': cube_name,        # Use cube name as table name (e.g., CoursePerformanceSummary)
            'dimensions': dimensions,
            'measures': measures
        }
    
    def _parse_dimensions(self, content: str) -> List[Dict[str, Any]]:
        """Extract dimensions from Cube.js file"""
        dimensions = []
        
        # Find dimensions block
        dimensions_match = re.search(
            r'dimensions:\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*?)\}',
            content,
            re.DOTALL
        )
        
        if not dimensions_match:
            print("  ⚠️  No dimensions block found")
            return dimensions
        
        dimensions_block = dimensions_match.group(1)
        
        # Parse individual dimensions
        dimension_pattern = r'(\w+):\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}(?=\s*,|\s*$)'
        matches = list(re.finditer(dimension_pattern, dimensions_block))
        
        print(f"  Found {len(matches)} dimensions in Cube.js file")
        
        for match in matches:
            dim_name = match.group(1)
            dim_content = match.group(2)
            
            # Extract sql field (actual column name)
            sql_match = re.search(r'sql:\s*`([^`]+)`', dim_content)
            column_name = sql_match.group(1).strip() if sql_match else dim_name
            
            # Extract type
            type_match = re.search(r'type:\s*[`"\']([^`"\']+)[`"\']', dim_content)
            dim_type = type_match.group(1) if type_match else 'string'
            
            # Extract title/description
            title_match = re.search(r'title:\s*[\'"]([^\'\"]+)[\'"]', dim_content)
            description = title_match.group(1) if title_match else dim_name.replace('_', ' ').title()
            
            verbose_name = dim_name.replace('_', ' ').title()
            
            dimensions.append({
                'column_name': column_name,
                'type': self._map_cube_type_to_superset(dim_type),
                'verbose_name': verbose_name,
                'description': description,
                'is_dttm': dim_type == 'time',
                'groupby': True,
                'filterable': True
            })
            
            print(f"    - {dim_name} ({column_name})")
        
        return dimensions
    
    def _parse_measures(self, content: str) -> List[Dict[str, Any]]:
        """Extract measures from Cube.js file"""
        measures = []
        
        # Find measures block
        measures_match = re.search(
            r'measures:\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*?)\}',
            content,
            re.DOTALL
        )
        
        if not measures_match:
            print("  ⚠️  No measures block found")
            return measures
        
        measures_block = measures_match.group(1)
        
        # Parse individual measures
        measure_pattern = r'(\w+):\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}(?=\s*,|\s*$)'
        matches = list(re.finditer(measure_pattern, measures_block))
        
        print(f"  Found {len(matches)} measures in Cube.js file")
        
        for match in matches:
            measure_name = match.group(1)
            measure_content = match.group(2)
            
            # Extract type
            type_match = re.search(r'type:\s*[`"\']([^`"\']+)[`"\']', measure_content)
            measure_type = type_match.group(1) if type_match else 'sum'
            
            # Extract sql
            sql_match = re.search(r'sql:\s*`([^`]+)`', measure_content)
            sql_expression = sql_match.group(1).strip() if sql_match else measure_name
            
            # Extract title
            title_match = re.search(r'title:\s*[\'"]([^\'\"]+)[\'"]', measure_content)
            metric_name = title_match.group(1) if title_match else measure_name.replace('_', ' ').title()
            
            # Map Cube.js aggregation type to SQL aggregate
            expression = self._create_metric_expression(measure_type, sql_expression)
            
            measures.append({
                'metric_name': metric_name,
                'expression': expression,
                'description': metric_name,
                'verbose_name': metric_name,
                'metric_type': measure_type
            })
            
            print(f"    - {metric_name}")
        
        return measures
    
    def _map_cube_type_to_superset(self, cube_type: str) -> str:
        """Map Cube.js types to Superset/SQL types"""
        type_mapping = {
            'string': 'VARCHAR',
            'number': 'NUMERIC',
            'time': 'TIMESTAMP',
            'boolean': 'BOOLEAN'
        }
        return type_mapping.get(cube_type, 'VARCHAR')
    
    def _create_metric_expression(self, agg_type: str, sql_expression: str) -> str:
        """Create SQL metric expression from Cube.js measure"""
        agg_mapping = {
            'sum': 'SUM',
            'avg': 'AVG',
            'count': 'COUNT',
            'min': 'MIN',
            'max': 'MAX',
            'count_distinct': 'COUNT(DISTINCT'
        }
        
        # Remove Cube.js ${} syntax and convert to plain SQL column references
        cleaned_expression = self._clean_cube_expression(sql_expression)
        
        agg_func = agg_mapping.get(agg_type, 'SUM')
        
        if agg_type == 'count_distinct':
            return f"{agg_func} {cleaned_expression})"
        else:
            return f"{agg_func}({cleaned_expression})"
    
    def _clean_cube_expression(self, expression: str) -> str:
        """Convert Cube.js expressions to SQL column references for Superset"""
        import re
        
        # Remove ${} syntax - convert ${column_name} to column_name
        cleaned = re.sub(r'\$\{([^}]+)\}', r'\1', expression)
        
        # Handle more complex expressions like arithmetic
        # Keep parentheses and operators but clean column references
        return cleaned
    
    def _create_or_update_dataset(self, schema_info: Dict[str, Any]) -> int:
        """Create a new dataset or update existing one"""
        # Check if dataset already exists
        existing_id = self._find_existing_dataset(
            schema_info['schema'],
            schema_info['table_name']
        )
        
        if existing_id:
            print(f"\\n🔄 Dataset already exists (ID: {existing_id}), updating...")
            self._update_dataset_metadata(existing_id, schema_info)
            return existing_id
        else:
            return self._create_new_dataset(schema_info)
    
    def _find_existing_dataset(self, schema_name: str, table_name: str) -> Optional[int]:
        """Find existing dataset by schema and table name"""
        dataset_url = f"{self.base_url}/api/v1/dataset/"
        params = {
            "q": json.dumps({
                "filters": [
                    {
                        "col": "table_name",
                        "opr": "eq",
                        "value": table_name
                    },
                    {
                        "col": "schema",
                        "opr": "eq",
                        "value": schema_name
                    },
                    {
                        "col": "database",
                        "opr": "rel_o_m",
                        "value": self.database_id
                    }
                ]
            })
        }
        
        response = self.session.get(dataset_url, params=params)
        if response.status_code == 200:
            results = response.json().get('result', [])
            if results:
                return results[0]['id']
        
        return None
    
    def _create_new_dataset(self, schema_info: Dict[str, Any]) -> int:
        """Create a new dataset in Superset"""
        dataset_url = f"{self.base_url}/api/v1/dataset/"
        
        # Create a simple table dataset (Cube.js will handle the actual data source)
        payload = {
            "database": self.database_id,
            "schema": schema_info['schema'],              # "public"
            "table_name": schema_info['table_name'],      # cube name like "CoursePerformanceSummary"
            "normalize_columns": False,
            "always_filter_main_dttm": False
        }
        
        print(f"\\n📊 Creating new dataset: {schema_info['table_name']}")
        response = self.session.post(dataset_url, json=payload)
        
        if response.status_code == 201:
            dataset_id = response.json()['id']
            print(f"✓ Dataset created with ID: {dataset_id}")
            
            # Update dataset with columns and metrics
            self._update_dataset_metadata(dataset_id, schema_info)
            
            return dataset_id
        else:
            print(f"✗ Failed to create dataset: {response.status_code}")
            print(f"Response: {response.text}")
            raise Exception(f"Failed to create dataset: {response.text}")
    
    def _update_dataset_metadata(self, dataset_id: int, schema_info: Dict[str, Any]):
        """Update dataset with column descriptions and metrics"""
        dataset_url = f"{self.base_url}/api/v1/dataset/{dataset_id}"
        
        # Refresh dataset to get all columns
        print(f"\\n🔄 Step 1: Refreshing dataset to fetch columns...")
        refresh_url = f"{self.base_url}/api/v1/dataset/{dataset_id}/refresh"
        self.session.put(refresh_url)
        time.sleep(2)  # Wait for refresh
        
        # Get current dataset info
        print(f"\\n📥 Step 2: Fetching dataset details...")
        response = self.session.get(dataset_url)
        if response.status_code != 200:
            print(f"✗ Failed to get dataset info: {response.status_code}")
            return
        
        dataset_data = response.json()['result']
        existing_columns = dataset_data.get('columns', [])
        existing_metrics = dataset_data.get('metrics', [])
        
        # Update columns
        print(f"\\n🏷️  Step 3: Updating column metadata...")
        updated_columns = self._update_columns(existing_columns, schema_info['dimensions'])
        
        # Update metrics
        print(f"\\n📊 Step 4: Adding metrics to dataset...")
        updated_metrics = self._update_metrics(existing_metrics, schema_info['measures'])
        
        # Send updates
        if updated_columns:
            print(f"\\n💾 Step 5: Saving updates...")
            update_payload = {
                'columns': updated_columns,
                'metrics': updated_metrics
            }
            
            response = self.session.put(dataset_url, json=update_payload)
            if response.status_code == 200:
                print(f"✓ Dataset updated successfully")
            else:
                print(f"✗ Failed to update dataset: {response.status_code}")
                print(f"Response: {response.text}")
    
    def _update_columns(self, existing_columns: List[dict], dimensions: List[dict]) -> List[dict]:
        """Update columns with metadata from dimensions"""
        updated_columns = []
        
        for col in existing_columns:
            col_name = col['column_name']
            
            # Find matching dimension
            matching_dim = next(
                (d for d in dimensions if d['column_name'].lower() == col_name.lower()),
                None
            )
            
            if matching_dim:
                # Clean and update column
                updated_col = {k: v for k, v in col.items() 
                             if k not in ['created_on', 'changed_on', 'type_generic', 'uuid', 'advanced_data_type']}
                
                updated_col.update({
                    'verbose_name': matching_dim['verbose_name'],
                    'description': matching_dim['description'],
                    'is_dttm': matching_dim['is_dttm'],
                    'groupby': matching_dim['groupby'],
                    'filterable': matching_dim['filterable'],
                    'is_active': True,
                    'expression': col.get('expression', ''),
                })
                
                updated_columns.append(updated_col)
                print(f"  ✓ {col_name} → '{matching_dim['verbose_name']}'")
            else:
                # Clean column but keep it
                clean_col = {k: v for k, v in col.items() 
                           if k not in ['created_on', 'changed_on', 'type_generic', 'uuid', 'advanced_data_type']}
                updated_columns.append(clean_col)
                print(f"  ○ {col_name} (no matching dimension)")
        
        return updated_columns
    
    def _update_metrics(self, existing_metrics: List[dict], measures: List[dict]) -> List[dict]:
        """Update metrics with new measures"""
        # Clean existing metrics and create a lookup by name
        updated_metrics = []
        existing_metric_names = {}
        
        for metric in existing_metrics:
            clean_metric = {k: v for k, v in metric.items() 
                          if k not in ['created_on', 'changed_on', 'uuid']}
            existing_metric_names[metric.get('metric_name')] = len(updated_metrics)
            updated_metrics.append(clean_metric)
        
        # Add or update metrics
        for measure in measures:
            metric_name = measure['metric_name']
            
            new_metric = {
                'metric_name': metric_name,
                'verbose_name': measure['verbose_name'],
                'expression': measure['expression'],
                'description': measure['description'],
                'metric_type': 'simple',
                'currency': None,
                'd3format': None,
                'extra': None,
                'warning_text': None
            }
            
            if metric_name in existing_metric_names:
                # Update existing metric
                index = existing_metric_names[metric_name]
                updated_metrics[index].update(new_metric)
                print(f"  ✓ Updated '{metric_name}': {measure['expression']}")
            else:
                # Add new metric
                updated_metrics.append(new_metric)
                print(f"  ✓ Added '{metric_name}': {measure['expression']}")
        
        return updated_metrics


# Register the Superset connector
ConnectorRegistry.register('superset', SupersetConnector)