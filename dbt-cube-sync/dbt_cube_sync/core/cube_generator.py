"""
Cube.js schema generator - creates Cube.js files from dbt models
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader, Template

from .models import DbtModel, CubeSchema, CubeDimension, CubeMeasure, CubePreAggregation, CubeRefreshKey
from .dbt_parser import DbtParser


class CubeGenerator:
    """Generates Cube.js schema files from dbt models"""
    
    def __init__(self, template_dir: str, output_dir: str):
        """
        Initialize the generator
        
        Args:
            template_dir: Directory containing Jinja2 templates
            output_dir: Directory to write generated Cube.js files
        """
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Jinja2 environment
        self.env = Environment(loader=FileSystemLoader(str(self.template_dir)))
    
    def generate_cube_files(self, models: List[DbtModel]) -> List[str]:
        """
        Generate Cube.js files for all models
        
        Args:
            models: List of DbtModel instances
            
        Returns:
            List of generated file paths
        """
        generated_files = []
        
        for model in models:
            try:
                cube_schema = self._convert_model_to_cube(model)
                file_path = self._write_cube_file(cube_schema)
                generated_files.append(str(file_path))
                print(f"✓ Generated: {file_path.name}")
            except Exception as e:
                print(f"✗ Error generating cube for {model.name}: {str(e)}")
        
        return generated_files
    
    def _convert_model_to_cube(self, model: DbtModel) -> CubeSchema:
        """Convert a dbt model to a Cube.js schema"""
        
        # Generate cube name (PascalCase)
        cube_name = self._to_pascal_case(model.name)
        
        # Generate SQL reference
        sql = f"SELECT * FROM {model.schema_name}.{model.name}"
        
        # Convert columns to dimensions
        dimensions = []
        for col_name, col_data in model.columns.items():
            cube_type = DbtParser.map_data_type_to_cube_type(col_data.data_type or '')
            
            dimension = CubeDimension(
                name=col_name,
                sql=col_name,
                type=cube_type,
                title=col_data.description or col_name.replace('_', ' ').title(),
                description=col_data.description or col_name.replace('_', ' ').title()
            )
            dimensions.append(dimension)
        
        # Convert explicitly defined metrics to measures
        measures = []
        for metric_name, metric_data in model.metrics.items():
            cube_type = DbtParser.map_dbt_type_to_cube_type(metric_data.type)
            
            # Generate SQL expression
            if metric_data.sql:
                sql_expr = metric_data.sql
            elif metric_data.type == 'count':
                sql_expr = "*"
            else:
                # Default to the metric name if no SQL provided
                sql_expr = metric_name
            
            measure = CubeMeasure(
                name=metric_name,
                type=cube_type,
                sql=sql_expr,
                title=metric_data.title or metric_name.replace('_', ' ').title(),
                description=metric_data.description or metric_name.replace('_', ' ').title()
            )
            measures.append(measure)
        
        # Convert pre-aggregations
        pre_aggregations = []
        for pre_agg_name, pre_agg_data in model.pre_aggregations.items():
            # Convert refresh_key if present
            refresh_key = None
            if pre_agg_data.refresh_key:
                refresh_key = CubeRefreshKey(
                    every=pre_agg_data.refresh_key.every,
                    sql=pre_agg_data.refresh_key.sql,
                    incremental=pre_agg_data.refresh_key.incremental,
                    update_window=pre_agg_data.refresh_key.update_window
                )
            
            pre_aggregation = CubePreAggregation(
                name=pre_agg_name,
                type=pre_agg_data.type,
                measures=pre_agg_data.measures,
                dimensions=pre_agg_data.dimensions,
                time_dimension=pre_agg_data.time_dimension,
                granularity=pre_agg_data.granularity,
                refresh_key=refresh_key
            )
            pre_aggregations.append(pre_aggregation)
        
        return CubeSchema(
            cube_name=cube_name,
            sql=sql,
            dimensions=dimensions,
            measures=measures,
            pre_aggregations=pre_aggregations
        )
    
    def _write_cube_file(self, cube_schema: CubeSchema) -> Path:
        """Write a Cube.js schema to file"""
        
        # Try to use template if available
        template_path = self.template_dir / 'cube_template.js'
        if template_path.exists():
            template = self.env.get_template('cube_template.js')
            content = template.render(
                cube_name=cube_schema.cube_name,
                sql=cube_schema.sql,
                dimensions=cube_schema.dimensions,
                measures=cube_schema.measures,
                pre_aggregations=cube_schema.pre_aggregations
            )
        else:
            # Fallback to hardcoded template
            content = self._generate_cube_content(cube_schema)
        
        # Write to file
        file_path = self.output_dir / f"{cube_schema.cube_name}.js"
        with open(file_path, 'w') as f:
            f.write(content)
        
        return file_path
    
    def _generate_cube_content(self, cube_schema: CubeSchema) -> str:
        """Generate Cube.js content using hardcoded template"""

        # Extract table name from SQL for refresh_key replacement
        import re
        table_name_match = re.search(r'FROM\s+([^\s,;]+)', cube_schema.sql, re.IGNORECASE)
        table_name = table_name_match.group(1) if table_name_match else None

        # Generate dimensions
        dimensions_content = []
        for dim in cube_schema.dimensions:
            dim_content = f"""    {dim.name}: {{
      sql: `{dim.sql}`,
      type: `{dim.type}`,
      title: '{dim.title}'
    }}"""
            dimensions_content.append(dim_content)
        
        # Generate measures  
        measures_content = []
        for measure in cube_schema.measures:
            measure_content = f"""    {measure.name}: {{
      type: `{measure.type}`,
      sql: `{measure.sql}`,
      title: '{measure.title}'
    }}"""
            measures_content.append(measure_content)
        
        # Generate pre-aggregations
        pre_aggregations_content = []
        for pre_agg in cube_schema.pre_aggregations:
            pre_agg_parts = [f"      type: `{pre_agg.type}`"]
            
            if pre_agg.measures:
                measures_list = ', '.join([f'CUBE.{measure}' for measure in pre_agg.measures])
                pre_agg_parts.append(f"      measures: [{measures_list}]")

            if pre_agg.dimensions:
                dims_list = ', '.join([f'CUBE.{dim}' for dim in pre_agg.dimensions])
                pre_agg_parts.append(f"      dimensions: [{dims_list}]")

            if pre_agg.time_dimension:
                pre_agg_parts.append(f"      time_dimension: CUBE.{pre_agg.time_dimension}")
                
            if pre_agg.granularity:
                pre_agg_parts.append(f"      granularity: `{pre_agg.granularity}`")
                
            if pre_agg.refresh_key:
                refresh_key_parts = []
                if pre_agg.refresh_key.every:
                    refresh_key_parts.append(f"        every: `{pre_agg.refresh_key.every}`")
                if pre_agg.refresh_key.sql:
                    # Replace ${CUBE} and ${this} with actual table name
                    refresh_sql = pre_agg.refresh_key.sql
                    if table_name:
                        refresh_sql = refresh_sql.replace('${CUBE}', table_name)
                        refresh_sql = refresh_sql.replace('${this}', table_name)
                    refresh_key_parts.append(f"        sql: `{refresh_sql}`")
                if pre_agg.refresh_key.incremental is not None:
                    refresh_key_parts.append(f"        incremental: {str(pre_agg.refresh_key.incremental).lower()}")
                if pre_agg.refresh_key.update_window:
                    refresh_key_parts.append(f"        update_window: `{pre_agg.refresh_key.update_window}`")
                
                if refresh_key_parts:
                    refresh_key_content = ',\n'.join(refresh_key_parts)
                    pre_agg_parts.append(f"      refresh_key: {{\n{refresh_key_content}\n      }}")
            
            parts_joined = ',\n'.join(pre_agg_parts)
            pre_agg_content = f"""    {pre_agg.name}: {{
{parts_joined}
    }}"""
            pre_aggregations_content.append(pre_agg_content)
        
        # Combine into full cube definition
        dimensions_joined = ',\n\n'.join(dimensions_content)
        measures_joined = ',\n\n'.join(measures_content)
        
        # Ensure we have measures (required for a useful Cube.js schema)
        if not measures_content:
            raise ValueError(f"Cube {cube_schema.cube_name} has no measures defined. Measures are required for Cube.js schemas.")
        
        if pre_aggregations_content:
            pre_aggregations_joined = ',\n\n'.join(pre_aggregations_content)
            content = f"""cube(`{cube_schema.cube_name}`, {{
  sql: `{cube_schema.sql}`,
  
  dimensions: {{
{dimensions_joined}
  }},
  
  measures: {{
{measures_joined}
  }},
  
  pre_aggregations: {{
{pre_aggregations_joined}
  }}
}});
"""
        else:
            content = f"""cube(`{cube_schema.cube_name}`, {{
  sql: `{cube_schema.sql}`,
  
  dimensions: {{
{dimensions_joined}
  }},
  
  measures: {{
{measures_joined}
  }}
}});
"""
        
        return content
    
    @staticmethod
    def _to_pascal_case(text: str) -> str:
        """Convert text to PascalCase"""
        # Remove non-alphanumeric characters and split
        words = re.sub(r'[^a-zA-Z0-9]', ' ', text).split()
        # Capitalize first letter of each word and join
        return ''.join(word.capitalize() for word in words if word)
    
    @staticmethod
    def _to_snake_case(text: str) -> str:
        """Convert text to snake_case"""
        # Replace non-alphanumeric with underscores and lowercase
        result = re.sub(r'[^a-zA-Z0-9]', '_', text).lower()
        # Remove multiple underscores
        return re.sub(r'_+', '_', result).strip('_')