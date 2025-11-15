"""
Cube.js schema generator - creates Cube.js files from dbt models
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader, Template

from .models import DbtModel, CubeSchema, CubeDimension, CubeMeasure
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
        
        return CubeSchema(
            cube_name=cube_name,
            sql=sql,
            dimensions=dimensions,
            measures=measures
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
                measures=cube_schema.measures
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
        
        # Combine into full cube definition
        dimensions_joined = ',\n\n'.join(dimensions_content)
        measures_joined = ',\n\n'.join(measures_content)
        
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