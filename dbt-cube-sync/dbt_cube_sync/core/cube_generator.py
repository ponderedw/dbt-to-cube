"""
Cube.js schema generator - creates Cube.js files from dbt models
"""
import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
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
    
    def generate_cube_files(
        self,
        models: List[DbtModel],
        stored_checksums: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str], Set[str]]:
        """
        Generate Cube.js files for all models.

        Args:
            models: List of DbtModel instances
            stored_checksums: Optional dict of node_id -> previously stored output_checksum.
                              When provided, a file is only written if its content changed.

        Returns:
            - file_paths: Dict[node_id -> file_path] for every model processed
            - output_checksums: Dict[node_id -> checksum] of the generated content
            - changed_node_ids: Set of node_ids whose content actually changed (file was written)
        """
        file_paths: Dict[str, str] = {}
        output_checksums: Dict[str, str] = {}
        changed_node_ids: Set[str] = set()

        for model in models:
            try:
                cube_schema = self._convert_model_to_cube(model)
                content = self._render_cube_content(cube_schema)
                checksum = hashlib.sha256(content.encode()).hexdigest()
                file_path = self.output_dir / f"{cube_schema.cube_name}.js"

                stored = (stored_checksums or {}).get(model.node_id)
                if not stored or stored != checksum or not file_path.exists():
                    with open(file_path, "w") as f:
                        f.write(content)
                    changed_node_ids.add(model.node_id)
                    print(f"  Generated: {file_path.name}")
                else:
                    print(f"  Unchanged: {file_path.name}")

                file_paths[model.node_id] = str(file_path)
                output_checksums[model.node_id] = checksum
            except Exception as e:
                print(f"  Error generating cube for {model.name}: {str(e)}")

        return file_paths, output_checksums, changed_node_ids
    
    def _convert_model_to_cube(self, model: DbtModel) -> CubeSchema:
        """Convert a dbt model to a Cube.js schema"""
        
        # Generate cube name (PascalCase)
        cube_name = self._to_pascal_case(model.name)
        
        # Generate SQL reference
        sql = f"SELECT * FROM {model.schema_name}.{model.alias}"
        
        # Convert columns to dimensions
        dimensions = []
        for col_name, col_data in model.columns.items():
            raw_type = col_data.data_type or ''
            cube_type = DbtParser.map_data_type_to_cube_type(raw_type)
            col_sql = self._safe_sql_expr(col_name, raw_type)

            label = (col_data.meta or {}).get('label')
            dimension = CubeDimension(
                name=col_name,
                sql=col_sql,
                type=cube_type,
                title=label or col_name.replace('_', ' ').title(),
                description=col_data.description
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
                description=metric_data.description
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
    
    def _render_cube_content(self, cube_schema: CubeSchema) -> str:
        """Render a Cube.js schema to a string without writing to disk."""
        template_path = self.template_dir / 'cube_template.js'
        if template_path.exists():
            template = self.env.get_template('cube_template.js')
            return template.render(
                cube_name=cube_schema.cube_name,
                sql=cube_schema.sql,
                dimensions=cube_schema.dimensions,
                measures=cube_schema.measures,
                pre_aggregations=cube_schema.pre_aggregations
            )
        return self._generate_cube_content(cube_schema)
    
    def _generate_cube_content(self, cube_schema: CubeSchema) -> str:
        """Generate Cube.js content using hardcoded template"""

        # Extract table name from SQL for refresh_key replacement
        import re
        table_name_match = re.search(r'FROM\s+([^\s,;]+)', cube_schema.sql, re.IGNORECASE)
        table_name = table_name_match.group(1) if table_name_match else None

        # Generate dimensions
        dimensions_content = []
        for dim in cube_schema.dimensions:
            dim_lines = [
                f"      sql: `{dim.sql}`",
                f"      type: `{dim.type}`",
                f"      title: `{dim.title}`",
            ]
            if dim.description:
                dim_lines.append(f"      description: `{dim.description}`")
            dim_content = f"    {dim.name}: {{\n" + ",\n".join(dim_lines) + "\n    }"
            dimensions_content.append(dim_content)
        
        # Generate measures  
        measures_content = []
        for measure in cube_schema.measures:
            measure_lines = [
                f"      type: `{measure.type}`",
                f"      sql: `{measure.sql}`",
                f"      title: `{measure.title}`",
            ]
            if measure.description:
                measure_lines.append(f"      description: `{measure.description}`")
            measure_content = f"    {measure.name}: {{\n" + ",\n".join(measure_lines) + "\n    }"
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
    def _safe_sql_expr(col_name: str, raw_type: str) -> str:
        """Return a SQL expression that is safe for Cube Store / Arrow Decimal128.

        Arrow Decimal128 has a maximum precision of 38. Two cases trigger the
        "precision > 38" error:
          - REAL/FLOAT columns: Cube infers decimal precision from IEEE-754 range.
            Fix: cast to DOUBLE PRECISION (Arrow FLOAT64, no precision cap).
          - NUMERIC(p, s) with p > 38: e.g. numeric(39, 10) from catalog.
            Fix: cap precision at 38 while preserving scale.
        """
        lower = raw_type.lower()

        if any(t in lower for t in ['real', 'float']):
            return f"CAST({col_name} AS DECIMAL(36, 10))"

        m = re.match(r'(?:numeric|decimal)\s*\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\)', lower)
        if m:
            precision = int(m.group(1))
            scale = int(m.group(2)) if m.group(2) else 0
            if precision > 38:
                return f"CAST({col_name} AS DECIMAL(38, {scale}))"

        return col_name

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