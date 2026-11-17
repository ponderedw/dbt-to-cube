"""
Cube.js schema generator - creates Cube.js YAML files from dbt models
"""
import hashlib
import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from jinja2 import Environment, FileSystemLoader, Template

from .models import DbtModel, CubeSchema, CubeDimension, CubeMeasure, CubePreAggregation, CubeRefreshKey, CubeJoin, CubeViewSchema
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
        # Remove any legacy .js files left over from older schema format
        for js_file in self.output_dir.glob('*.js'):
            js_file.unlink()
            print(f"  Removed legacy file: {js_file.name}")

        file_paths: Dict[str, str] = {}
        output_checksums: Dict[str, str] = {}
        changed_node_ids: Set[str] = set()

        for model in models:
            try:
                cube_schema = self._convert_model_to_cube(model)
                content = self._render_cube_content(cube_schema)
                checksum = hashlib.sha256(content.encode()).hexdigest()
                file_path = self.output_dir / f"{cube_schema.cube_name}.yaml"

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

    def generate_view_files(self, views: List[CubeViewSchema]) -> List[str]:
        """Write Cube.js view YAML files and return list of written file paths."""
        written = []
        for view in views:
            content = self._generate_view_yaml(view)
            file_path = self.output_dir / f"{view.view_name}.yaml"
            file_path.write_text(content)
            print(f"  Generated view: {file_path.name}")
            written.append(str(file_path))
        return written

    def _generate_view_yaml(self, view: CubeViewSchema) -> str:
        """Render a Cube.js view definition to YAML."""
        view_def: Dict[str, Any] = {'name': view.view_name}
        if view.description:
            view_def['description'] = view.description
        if view.cubes:
            view_def['cubes'] = view.cubes
        if view.measures:
            view_def['measures'] = view.measures
        if view.access_policy:
            view_def['access_policy'] = view.access_policy
        return yaml.dump({'views': [view_def]}, default_flow_style=False,
                         allow_unicode=True, sort_keys=False)

    def _convert_model_to_cube(self, model: DbtModel) -> CubeSchema:
        """Convert a dbt model to a Cube.js schema"""
        
        # Generate cube name (PascalCase)
        cube_name = self._to_pascal_case(model.name)
        
        # Generate SQL reference
        sql = f"SELECT * FROM {model.schema_name}.{model.alias}"
        
        # Convert columns to dimensions (sorted by name for deterministic output)
        dimensions = []
        for col_name, col_data in sorted(model.columns.items()):
            raw_type = col_data.data_type or ''
            cube_type = DbtParser.map_data_type_to_cube_type(raw_type)
            col_sql = self._safe_sql_expr(col_data.sql or col_name, raw_type)

            meta = col_data.meta or {}
            label = meta.get('label')
            is_pk = bool(meta.get('primary-key'))
            dimension = CubeDimension(
                name=col_name,
                sql=col_sql,
                type=cube_type,
                title=label or col_name.replace('_', ' ').title(),
                description=col_data.description,
                primary_key=is_pk,
                public=True if is_pk else None,
            )
            dimensions.append(dimension)
        
        # Convert explicitly defined metrics to measures (sorted for deterministic output)
        measures = []
        for metric_name, metric_data in sorted(model.metrics.items()):
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
                description=metric_data.description,
                format=metric_data.format,
                filters=metric_data.filters,
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
            pre_aggregations=pre_aggregations,
            joins=sorted(model.joins, key=lambda j: j.name) if model.joins else model.joins,
            access_policy=model.access_policy,
        )
    
    def _render_cube_content(self, cube_schema: CubeSchema) -> str:
        """Render a Cube.js YAML schema to a string without writing to disk."""
        template_path = self.template_dir / 'cube_template.yaml'
        if template_path.exists():
            template = self.env.get_template('cube_template.yaml')
            return template.render(
                cube_name=cube_schema.cube_name,
                sql=cube_schema.sql,
                dimensions=cube_schema.dimensions,
                measures=cube_schema.measures,
                pre_aggregations=cube_schema.pre_aggregations,
                joins=cube_schema.joins,
                access_policy=cube_schema.access_policy,
            )
        return self._generate_cube_yaml(cube_schema)
    
    def _generate_cube_yaml(self, cube_schema: CubeSchema) -> str:
        """Generate Cube.js YAML data model content."""
        if not cube_schema.measures:
            raise ValueError(
                f"Cube {cube_schema.cube_name} has no measures defined. "
                "Measures are required for Cube.js schemas."
            )

        cube: dict = {'name': cube_schema.cube_name, 'sql': cube_schema.sql}

        if cube_schema.joins:
            cube['joins'] = [
                {
                    'name': j.name,
                    'sql': self._normalize_cube_ref(j.sql),
                    'relationship': j.relationship,
                }
                for j in cube_schema.joins
            ]

        if cube_schema.dimensions:
            dims = []
            for d in cube_schema.dimensions:
                entry: dict = {'name': d.name, 'sql': d.sql, 'type': d.type, 'title': d.title}
                if d.primary_key:
                    entry['primary_key'] = True
                if d.public is not None:
                    entry['public'] = d.public
                if d.description:
                    entry['description'] = d.description
                dims.append(entry)
            cube['dimensions'] = dims

        measures = []
        for m in cube_schema.measures:
            entry = {'name': m.name, 'type': m.type, 'title': m.title}
            if m.sql:
                entry['sql'] = m.sql
            if m.description:
                entry['description'] = m.description
            if m.format:
                entry['format'] = m.format
            if m.filters:
                entry['filters'] = [{'sql': f} for f in m.filters]
            measures.append(entry)
        cube['measures'] = measures

        if cube_schema.pre_aggregations:
            pre_aggs = []
            for pa in cube_schema.pre_aggregations:
                entry = {'name': pa.name, 'type': pa.type}
                if pa.measures:
                    entry['measures'] = [f'CUBE.{m}' for m in pa.measures]
                if pa.dimensions:
                    entry['dimensions'] = [f'CUBE.{d}' for d in pa.dimensions]
                if pa.time_dimension:
                    entry['time_dimension'] = f'CUBE.{pa.time_dimension}'
                if pa.granularity:
                    entry['granularity'] = pa.granularity
                if pa.refresh_key:
                    rk: dict = {}
                    if pa.refresh_key.every:
                        rk['every'] = pa.refresh_key.every
                    if pa.refresh_key.sql:
                        rk['sql'] = self._normalize_cube_ref(pa.refresh_key.sql)
                    if pa.refresh_key.incremental is not None:
                        rk['incremental'] = pa.refresh_key.incremental
                    if pa.refresh_key.update_window:
                        rk['update_window'] = pa.refresh_key.update_window
                    if rk:
                        entry['refresh_key'] = rk
                pre_aggs.append(entry)
            cube['pre_aggregations'] = pre_aggs

        if cube_schema.access_policy:
            cube['access_policy'] = cube_schema.access_policy

        return yaml.dump(
            {'cubes': [cube]},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    @staticmethod
    def _normalize_cube_ref(sql: str) -> str:
        """Convert JS template literal cube refs (${X}) to YAML refs ({X})."""
        return sql.replace('${', '{') if sql else sql

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