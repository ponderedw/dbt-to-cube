import os
import re
import json
import requests
import time
from typing import Dict, List, Any, Optional
from pathlib import Path

class SupersetDatasetManager:
    def __init__(self, superset_url: str, username: str, password: str):
        """
        Initialize Superset Dataset Manager
        
        Args:
            superset_url: Base URL of Superset instance (e.g., 'http://localhost:8088')
            username: Superset username
            password: Superset password
        """
        self.base_url = superset_url.rstrip('/')
        self.session = requests.Session()
        self.access_token = None
        self.csrf_token = None
        self.database_id = None
        
        # Login and get tokens
        self._login(username, password)
        self._get_csrf_token()
        self._get_database_id("Cube")
    
    def _login(self, username: str, password: str):
        """Authenticate and get JWT token"""
        login_url = f"{self.base_url}/api/v1/security/login"
        payload = {
            "username": username,
            "password": password,
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
    
    def _get_database_id(self, database_name: str):
        """Get database ID by name"""
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
    
    def _find_existing_dataset(self, schema_name: str, table_name: str) -> Optional[int]:
        """
        Find existing dataset by schema and table name
        
        Returns:
            Dataset ID if found, None otherwise
        """
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
    
    def parse_cube_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parse Cube.js schema file and extract metadata
        
        Args:
            file_path: Path to the Cube.js file
            
        Returns:
            Dictionary containing parsed schema information
        """
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Extract cube name
        cube_name_match = re.search(r'cube\s*\(\s*[`"\']([^`"\']+)[`"\']', content)
        if not cube_name_match:
            raise ValueError(f"Could not find cube name in {file_path}")
        
        cube_name = cube_name_match.group(1)
        
        # Always use public schema and cube name as table name
        schema_name = "public"
        table_name = cube_name
        
        print(f"  Cube: {cube_name}")
        print(f"  Schema: {schema_name}")
        print(f"  Table: {table_name}")
        
        # Parse dimensions
        dimensions = self._parse_dimensions(content)
        
        # Parse measures
        measures = self._parse_measures(content)
        
        return {
            'cube_name': cube_name,
            'schema': schema_name,
            'table_name': table_name,
            'dimensions': dimensions,
            'measures': measures
        }
    
    def _parse_dimensions(self, content: str) -> List[Dict[str, Any]]:
        """Extract dimensions from Cube.js file"""
        dimensions = []
        
        # Find dimensions block - improved regex to handle nested braces
        dimensions_match = re.search(
            r'dimensions:\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}',
            content,
            re.DOTALL
        )
        
        if not dimensions_match:
            print("  ⚠️  No dimensions block found")
            return dimensions
        
        dimensions_block = dimensions_match.group(1)
        
        # Parse individual dimensions - improved to handle nested objects
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
        
        # Find measures block - improved regex
        measures_match = re.search(
            r'measures:\s*\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}',
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
        
        agg_func = agg_mapping.get(agg_type, 'SUM')
        
        if agg_type == 'count_distinct':
            return f"{agg_func} {sql_expression})"
        else:
            return f"{agg_func}({sql_expression})"
    
    def create_or_update_dataset(self, schema_info: Dict[str, Any]) -> int:
        """
        Create a new dataset or update existing one
        
        Args:
            schema_info: Parsed schema information from parse_cube_file
            
        Returns:
            Dataset ID
        """
        # Check if dataset already exists
        existing_id = self._find_existing_dataset(
            schema_info['schema'],
            schema_info['table_name']
        )
        
        if existing_id:
            print(f"\n🔄 Dataset already exists (ID: {existing_id}), updating...")
            self._update_dataset_metadata(existing_id, schema_info)
            return existing_id
        else:
            return self._create_new_dataset(schema_info)
    
    def _create_new_dataset(self, schema_info: Dict[str, Any]) -> int:
        """Create a new dataset in Superset"""
        dataset_url = f"{self.base_url}/api/v1/dataset/"
        
        payload = {
            "database": self.database_id,
            "schema": schema_info['schema'],
            "table_name": schema_info['table_name'],
            "normalize_columns": False,
            "always_filter_main_dttm": False
        }
        
        print(f"\n📊 Creating new dataset: {schema_info['table_name']}")
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
        
        print(f"\n🔄 Step 1: Refreshing dataset to fetch columns...")
        # First, refresh the dataset to get all columns from the database
        refresh_url = f"{self.base_url}/api/v1/dataset/{dataset_id}/refresh"
        refresh_response = self.session.put(refresh_url)
        
        if refresh_response.status_code == 200:
            print(f"✓ Dataset refreshed successfully")
        else:
            print(f"⚠️  Warning: Refresh returned {refresh_response.status_code}")
        
        # Wait for refresh to complete
        time.sleep(2)
        
        # Get current dataset info with all columns
        print(f"\n📥 Step 2: Fetching dataset details...")
        response = self.session.get(dataset_url)
        
        if response.status_code != 200:
            print(f"✗ Failed to get dataset info: {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        dataset_data = response.json()['result']
        existing_columns = dataset_data.get('columns', [])
        existing_metrics = dataset_data.get('metrics', [])
        
        print(f"  • Found {len(existing_columns)} columns")
        print(f"  • Found {len(existing_metrics)} existing metrics")
        
        # Step 3: Update columns with metadata
        print(f"\n🏷️  Step 3: Updating column metadata...")
        updated_columns = []
        
        for col in existing_columns:
            col_name = col['column_name']
            
            # Find matching dimension from Cube.js (case-insensitive)
            matching_dim = next(
                (d for d in schema_info['dimensions'] 
                 if d['column_name'].lower() == col_name.lower()),
                None
            )
            
            if matching_dim:
                # Only include fields that can be updated (exclude read-only fields)
                updated_col = {
                    'id': col.get('id'),
                    'column_name': col_name,
                    'verbose_name': matching_dim['verbose_name'],
                    'description': matching_dim['description'],
                    'type': col.get('type'),
                    'is_dttm': matching_dim['is_dttm'],
                    'groupby': matching_dim['groupby'],
                    'filterable': matching_dim['filterable'],
                    'is_active': True,
                    'expression': col.get('expression', ''),
                    'python_date_format': col.get('python_date_format'),
                    'extra': col.get('extra')
                }
                # Remove read-only fields that cause validation errors
                for readonly_field in ['created_on', 'changed_on', 'type_generic', 'uuid', 'advanced_data_type']:
                    updated_col.pop(readonly_field, None)
                
                updated_columns.append(updated_col)
                print(f"  ✓ {col_name} → '{matching_dim['verbose_name']}'")
            else:
                # Keep column but clean read-only fields
                clean_col = {k: v for k, v in col.items() 
                           if k not in ['created_on', 'changed_on', 'type_generic', 'uuid', 'advanced_data_type']}
                updated_columns.append(clean_col)
                print(f"  ○ {col_name} (no matching dimension)")
        
        # Update columns first
        print(f"\n💾 Step 4: Saving column updates...")
        update_payload = {
            'columns': updated_columns
        }
        
        response = self.session.put(dataset_url, json=update_payload)
        
        if response.status_code == 200:
            print(f"✓ Columns updated successfully")
            updated_count = sum(1 for col in updated_columns 
                              if any(d['column_name'].lower() == col['column_name'].lower() 
                                    for d in schema_info['dimensions']))
            print(f"  • Updated {updated_count} columns with metadata")
        else:
            print(f"⚠️  Warning: Column update returned {response.status_code}")
            print(f"Response: {response.text}")
        
        # Step 5: Add metrics by updating the dataset with new metrics
        print(f"\n📊 Step 5: Adding metrics to dataset...")
        
        # Get existing metric names to avoid duplicates
        existing_metric_names = {m.get('metric_name') for m in existing_metrics}
        
        # Create new metrics list with existing and new metrics
        new_metrics = []
        added_metrics = 0
        skipped_metrics = 0
        
        # Keep existing metrics (clean read-only fields)
        for metric in existing_metrics:
            clean_metric = {k: v for k, v in metric.items() 
                          if k not in ['created_on', 'changed_on', 'uuid']}
            new_metrics.append(clean_metric)
        
        # Add new metrics
        for measure in schema_info['measures']:
            metric_name = measure['metric_name']
            
            if metric_name in existing_metric_names:
                print(f"  ⊘ Skipping '{metric_name}' (already exists)")
                skipped_metrics += 1
                continue
            
            # Create new metric object matching API schema
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
            
            new_metrics.append(new_metric)
            print(f"  ✓ Prepared '{metric_name}': {measure['expression']}")
            added_metrics += 1
        
        # Update dataset with new metrics if any were added
        if added_metrics > 0:
            print(f"\n💾 Step 6: Updating dataset with {added_metrics} new metrics...")
            
            metrics_update_payload = {
                'metrics': new_metrics
            }
            
            response = self.session.put(dataset_url, json=metrics_update_payload)
            
            if response.status_code == 200:
                print(f"✓ Successfully added {added_metrics} metrics")
            else:
                print(f"✗ Failed to update metrics: {response.status_code}")
                print(f"Response: {response.text}")
                # Try alternative approach if PUT fails
                self._try_alternative_metric_creation(dataset_id, schema_info['measures'], existing_metric_names)
        else:
            print(f"  ⊘ No new metrics to add")
        
        # Final summary
        print(f"\n✅ Dataset update complete!")
        print(f"   📋 Columns: {len(updated_columns)} total")
        print(f"   📊 Metrics: {added_metrics} added, {skipped_metrics} skipped, {len(existing_metrics)} existing")
    
    def _try_alternative_metric_creation(self, dataset_id: int, measures: List[Dict[str, Any]], existing_metric_names: set):
        """Alternative approach to create metrics using different endpoints or methods"""
        print(f"\n🔄 Trying alternative metric creation approach...")
        
        for measure in measures:
            metric_name = measure['metric_name']
            
            if metric_name in existing_metric_names:
                continue
            
            # Try creating via SQL Lab saved query approach or direct SQL metric creation
            try:
                # Method 1: Try creating a SQL metric via dataset endpoint with SQL expression
                metric_data = {
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
                
                # Try updating the dataset by adding one metric at a time
                dataset_url = f"{self.base_url}/api/v1/dataset/{dataset_id}"
                response = self.session.get(dataset_url)
                
                if response.status_code == 200:
                    current_data = response.json()['result']
                    current_metrics = current_data.get('metrics', [])
                    
                    # Clean existing metrics
                    clean_current_metrics = []
                    for metric in current_metrics:
                        clean_metric = {k: v for k, v in metric.items() 
                                      if k not in ['created_on', 'changed_on', 'uuid']}
                        clean_current_metrics.append(clean_metric)
                    
                    clean_current_metrics.append(metric_data)
                    
                    update_payload = {
                        'metrics': clean_current_metrics
                    }
                    
                    response = self.session.put(dataset_url, json=update_payload)
                    
                    if response.status_code == 200:
                        print(f"  ✓ Added '{metric_name}' via alternative method")
                    else:
                        print(f"  ✗ Alternative method also failed for '{metric_name}': {response.status_code}")
                        print(f"    Response: {response.text}")
                
            except Exception as e:
                print(f"  ✗ Exception during alternative creation for '{metric_name}': {str(e)}")
                continue
    
    def process_cube_folder(self, folder_path: str):
        """
        Process all Cube.js files in a folder
        
        Args:
            folder_path: Path to folder containing Cube.js files
        """
        folder = Path(folder_path)
        
        if not folder.exists():
            raise ValueError(f"Folder not found: {folder_path}")
        
        cube_files = list(folder.glob("*.js"))
        
        if not cube_files:
            print(f"No .js files found in {folder_path}")
            return
        
        print(f"\n🔍 Found {len(cube_files)} Cube.js files")
        
        results = []
        
        for cube_file in cube_files:
            try:
                print(f"\n{'='*60}")
                print(f"Processing: {cube_file.name}")
                print(f"{'='*60}")
                
                schema_info = self.parse_cube_file(str(cube_file))
                dataset_id = self.create_or_update_dataset(schema_info)
                
                results.append({
                    'file': cube_file.name,
                    'dataset_id': dataset_id,
                    'status': 'success'
                })
                
            except Exception as e:
                print(f"✗ Error processing {cube_file.name}: {str(e)}")
                import traceback
                traceback.print_exc()
                results.append({
                    'file': cube_file.name,
                    'error': str(e),
                    'status': 'failed'
                })
        
        # Print summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'failed')
        print(f"✓ Successful: {successful}")
        print(f"✗ Failed: {failed}")
        print(f"Total: {len(results)}")
        
        # Show detailed results
        if successful > 0:
            print(f"\n✅ Successfully processed:")
            for r in results:
                if r['status'] == 'success':
                    print(f"   • {r['file']} (Dataset ID: {r['dataset_id']})")
        
        if failed > 0:
            print(f"\n❌ Failed to process:")
            for r in results:
                if r['status'] == 'failed':
                    print(f"   • {r['file']}: {r.get('error', 'Unknown error')}")


# Usage example
if __name__ == "__main__":
    # Configuration
    SUPERSET_URL = "http://localhost:8088"
    USERNAME = "admin"
    PASSWORD = "admin"
    CUBE_FILES_FOLDER = "./cube/conf/cubes_correct"  # Path to your folder with Cube.js files
    
    # Initialize manager
    manager = SupersetDatasetManager(
        superset_url=SUPERSET_URL,
        username=USERNAME,
        password=PASSWORD
    )
    
    # Process all Cube.js files in the folder
    manager.process_cube_folder(CUBE_FILES_FOLDER)
    
    # Or process a single file
    # schema_info = manager.parse_cube_file("./CoursePerformanceSummary.js")
    # dataset_id = manager.create_or_update_dataset(schema_info)