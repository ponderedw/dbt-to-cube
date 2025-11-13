import json
import re
import os
from pathlib import Path


def extract_metrics_from_manifest(json_file_path, catalog_file_path=None):
    """
    Extract metrics from dbt manifest JSON file.
    Looks for metrics in nodes[*].config.meta.metrics structure.
    
    Args:
        json_file_path: Path to the manifest JSON file
        catalog_file_path: Optional path to the catalog JSON file for column types
        
    Returns:
        A list of dictionaries containing model information with their metrics
    """
    with open(json_file_path, 'r') as f:
        manifest = json.load(f)
    
    # Load catalog for column type information if available
    catalog = None
    if catalog_file_path and os.path.exists(catalog_file_path):
        try:
            with open(catalog_file_path, 'r') as f:
                catalog = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load catalog file {catalog_file_path}: {e}")
    
    models_with_metrics = []
    
    # Search through all nodes (models)
    nodes = manifest.get('nodes', {})
    
    for node_id, node_data in nodes.items():
        # Only process models
        if node_data.get('resource_type') != 'model':
            continue
            
        # Get model information
        model_name = node_data.get('name', '')
        model_schema = node_data.get('schema', '')
        model_database = node_data.get('database', '')
        
        # Look for metrics in config.meta.metrics
        config = node_data.get('config', {})
        meta = config.get('meta', {})
        metrics = meta.get('metrics', {})
        
        # Get columns for dimensions from manifest (only explicitly defined columns)
        columns = node_data.get('columns', {})
        
        # Enhance columns with catalog information if available, but only for explicitly defined columns
        if catalog and node_id in catalog.get('nodes', {}):
            catalog_columns = catalog['nodes'][node_id].get('columns', {})
            # Only merge catalog information for columns that are explicitly defined in models.yml
            enhanced_columns = {}
            for col_name in columns.keys():
                enhanced_columns[col_name] = columns[col_name].copy()
                if col_name in catalog_columns:
                    enhanced_columns[col_name]['data_type'] = catalog_columns[col_name].get('type', '')
            
            columns = enhanced_columns
        
        # Only include models that have metrics and explicitly defined columns
        if metrics and columns:
            models_with_metrics.append({
                'model_name': model_name,
                'database': model_database,
                'schema': model_schema,
                'metrics': metrics,
                'columns': columns,
                'node_id': node_id
            })
    
    return models_with_metrics


def map_dbt_type_to_cube_type(dbt_type):
    """
    Map dbt metric types to Cube.js measure types.
    
    Args:
        dbt_type: The type from dbt (sum, average, count, etc.)
        
    Returns:
        Cube.js measure type
    """
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


def map_format_to_cube_format(format_str):
    """
    Map format strings to valid Cube.js format values.
    
    Args:
        format_str: The format string from dbt (e.g., '0.0%', '$#,##0', etc.)
        
    Returns:
        Valid Cube.js format value: 'percent', 'currency', 'number', or None
    """
    if not format_str:
        return None
    
    format_lower = format_str.lower()
    
    # Check for percentage formats
    if '%' in format_str or 'percent' in format_lower:
        return 'percent'
    
    # Check for currency formats
    if any(symbol in format_str for symbol in ['$', '€', '£', '¥']) or 'currency' in format_lower:
        return 'currency'
    
    # Check for number formats
    if any(char in format_str for char in ['#', '0', ',']) or 'number' in format_lower:
        return 'number'
    
    # Default to number for other formats
    return 'number'


def infer_dimension_type(column_info):
    """
    Infer Cube.js dimension type from column data type.
    
    Args:
        column_info: Dictionary with column information
        
    Returns:
        Cube.js dimension type
    """
    data_type = column_info.get('data_type') if column_info else None
    
    if not data_type:
        return 'string'
    
    data_type = data_type.lower()
    
    # Map SQL types to Cube.js types
    if any(t in data_type for t in ['int', 'integer', 'bigint', 'numeric', 'decimal', 'float', 'double', 'real']):
        return 'number'
    elif any(t in data_type for t in ['timestamp', 'datetime', 'date']):
        return 'time'
    elif 'bool' in data_type:
        return 'boolean'
    else:
        return 'string'


def clean_sql_reference(sql):
    """
    Clean SQL references like ${column_name} to just column_name for Cube.js.
    
    Args:
        sql: SQL string with ${} references
        
    Returns:
        Cleaned SQL string
    """
    # Replace ${column_name} with column_name
    cleaned = re.sub(r'\$\{([^}]+)\}', r'\1', sql)
    return cleaned


def generate_cube_file(model_info, output_dir='./cubes'):
    """
    Generate a Cube.js file for a given model with its metrics and dimensions.
    
    Args:
        model_info: Dictionary containing model information including metrics and columns
        output_dir: Directory to save the generated Cube.js files
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate cube name from model name (PascalCase)
    cube_name = to_pascal_case(model_info['model_name'])
    
    # Generate file name
    file_name = f"{cube_name}.js"
    file_path = os.path.join(output_dir, file_name)
    
    # Generate SQL query
    schema = model_info.get('schema', 'public')
    database = model_info.get('database', 'dev')
    table_name = model_info['model_name']
    
    sql_query = f"SELECT * FROM {database}.{schema}.{table_name}"
    
    # Generate dimensions section
    dimensions_code = generate_dimensions_code(model_info['columns'])
    
    # Generate measures section
    measures_code = generate_measures_code(model_info['metrics'])
    
    # Generate the Cube.js content
    cube_content = f"""cube(`{cube_name}`, {{
  sql: `{sql_query}`,
  
  dimensions: {{
{dimensions_code}
  }},
  
  measures: {{
{measures_code}
  }},
  
  refreshKey: {{
    every: `1 hour`,
  }},
}});
"""
    
    # Write to file
    with open(file_path, 'w') as f:
        f.write(cube_content)
    
    return file_path


def generate_dimensions_code(columns):
    """
    Generate the dimensions section code for Cube.js.
    
    Args:
        columns: Dictionary of column information
        
    Returns:
        String with formatted dimensions code
    """
    if not columns:
        return "    // No dimensions defined"
    
    dimensions = []
    
    for col_name, col_info in columns.items():
        dimension_type = infer_dimension_type(col_info)
        description = col_info.get('description', '')
        
        # Format description as title for JS
        title_line = ""
        if description:
            # Escape quotes and newlines
            description = description.replace('\\', '\\\\').replace("'", "\\'").replace('\n', ' ')
            title_line = f"\n      title: '{description}',"
        
        dimension_code = f"""    {col_name}: {{
      sql: `{col_name}`,
      type: `{dimension_type}`,{title_line}
    }}"""
        
        dimensions.append(dimension_code)
    
    return ",\n    \n".join(dimensions)


def generate_measures_code(metrics):
    """
    Generate the measures section code for Cube.js.
    
    Args:
        metrics: Dictionary of metric definitions
        
    Returns:
        String with formatted measures code
    """
    if not metrics:
        return "    // No measures defined"
    
    measures = []
    
    for metric_name, metric_config in metrics.items():
        metric_type = metric_config.get('type', 'sum')
        cube_type = map_dbt_type_to_cube_type(metric_type)
        
        label = metric_config.get('label', metric_name)
        sql = metric_config.get('sql', metric_name)
        format_str = metric_config.get('format', '')
        
        # Clean SQL references
        sql = clean_sql_reference(sql)
        
        # Escape quotes in label
        label = label.replace('\\', '\\\\').replace("'", "\\'")
        
        # Build measure code
        measure_code = f"""    {metric_name}: {{
      type: `{cube_type}`,
      sql: `{sql}`,
      title: '{label}',"""
        
        # Add format if present, mapping to valid Cube.js format values
        if format_str:
            cube_format = map_format_to_cube_format(format_str)
            if cube_format:
                measure_code += f"\n      format: `{cube_format}`,"
        
        measure_code += "\n    }"
        
        measures.append(measure_code)
    
    return ",\n    \n".join(measures)


def to_pascal_case(snake_str):
    """Convert snake_case to PascalCase."""
    components = snake_str.split('_')
    return ''.join(x.title() for x in components)


def main():
    # Path to your manifest JSON file
    manifest_path = 'DbtEducationalDataProject/target/manifest.json'
    catalog_path = 'DbtEducationalDataProject/target/catalog.json'
    
    print("Extracting models with metrics from manifest...")
    models = extract_metrics_from_manifest(manifest_path, catalog_path)
    
    print(f"\nFound {len(models)} models with metrics:")
    for model in models:
        print(f"  - {model['model_name']}: {len(model['metrics'])} metrics, {len(model['columns'])} dimensions")
        for metric_name in model['metrics'].keys():
            print(f"      * {metric_name}")
    
    # Generate Cube.js files
    print("\nGenerating Cube.js files...")
    output_dir = './cubes_correct'
    
    generated_files = []
    for model in models:
        file_path = generate_cube_file(model, output_dir)
        generated_files.append(file_path)
        print(f"  Created: {os.path.basename(file_path)}")
    
    print(f"\n✓ Generated {len(generated_files)} Cube.js files in {output_dir}")
    
    # Create a summary file
    summary_path = os.path.join(output_dir, 'README.md')
    with open(summary_path, 'w') as f:
        f.write("# Generated Cube.js Files\n\n")
        f.write(f"Total cubes generated: {len(models)}\n\n")
        
        for model in models:
            f.write(f"## {to_pascal_case(model['model_name'])}\n\n")
            f.write(f"**Source Table:** `{model['database']}.{model['schema']}.{model['model_name']}`\n\n")
            
            f.write(f"**Metrics ({len(model['metrics'])}):**\n")
            for metric_name, metric_config in model['metrics'].items():
                label = metric_config.get('label', metric_name)
                metric_type = metric_config.get('type', 'sum')
                f.write(f"- `{metric_name}` - {label} ({metric_type})\n")
            
            f.write(f"\n**Dimensions ({len(model['columns'])}):**\n")
            for col_name, col_info in model['columns'].items():
                desc = col_info.get('description', '')
                if desc:
                    f.write(f"- `{col_name}` - {desc}\n")
                else:
                    f.write(f"- `{col_name}`\n")
            
            f.write("\n---\n\n")
    
    print(f"\n✓ Summary saved to: {summary_path}")


if __name__ == '__main__':
    main()
