"""
CLI interface for dbt-cube-sync tool
"""
import click
import sys
from pathlib import Path
from typing import Optional

from .core.dbt_parser import DbtParser
from .core.cube_generator import CubeGenerator
from .connectors.base import ConnectorRegistry
from .config import Config

# Import connectors to register them
from .connectors import superset, tableau, powerbi


class CustomGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        # Handle common mistake of typing dbt-cube-sync twice
        if cmd_name == 'dbt-cube-sync':
            click.echo("❌ Error: You typed 'dbt-cube-sync' twice!")
            click.echo("💡 Just run: dbt-cube-sync <command>")
            click.echo("\nAvailable commands:")
            click.echo("  dbt-cube-sync --help                                    # Show help")
            click.echo("  dbt-cube-sync --version                                 # Show version")
            click.echo("  dbt-cube-sync dbt-to-cube -m manifest -c catalog -o output # Generate with catalog")
            click.echo("  dbt-cube-sync dbt-to-cube -m manifest -s postgresql://user:pass@host/db -o output # Generate with database")
            click.echo("  dbt-cube-sync dbt-to-cube -m manifest -s <uri> --models model1,model2 -o output # Filter specific models")
            click.echo("  dbt-cube-sync cube-to-bi superset -c cubes -u url -n user -p pass -d Cube # Sync to BI tool")
            ctx.exit(1)

        return super().get_command(ctx, cmd_name)


@click.group(cls=CustomGroup)
@click.version_option()
def main():
    """dbt-cube-sync: Synchronization tool for dbt models to Cube.js schemas and BI tools"""
    pass


@main.command()
@click.option('--manifest', '-m',
              required=True,
              help='Path to dbt manifest.json file')
@click.option('--catalog', '-c',
              required=False,
              default=None,
              help='Path to dbt catalog.json file (optional if --sqlalchemy-uri is provided)')
@click.option('--sqlalchemy-uri', '-s',
              required=False,
              default=None,
              help='SQLAlchemy database URI for fetching column types (e.g., postgresql://user:pass@host:port/db)')
@click.option('--models',
              required=False,
              default=None,
              help='Comma-separated list of model names to process (e.g., model1,model2). If not specified, processes all models')
@click.option('--output', '-o',
              required=True,
              help='Output directory for Cube.js files')
@click.option('--template-dir', '-t',
              default='./cube/templates',
              help='Directory containing Cube.js templates')
def dbt_to_cube(manifest: str, catalog: Optional[str], sqlalchemy_uri: Optional[str], models: Optional[str], output: str, template_dir: str):
    """Generate Cube.js schemas from dbt models"""
    try:
        # Validate that at least one source of column types is provided
        if not catalog and not sqlalchemy_uri:
            click.echo("❌ Error: You must provide either --catalog or --sqlalchemy-uri to get column data types", err=True)
            click.echo("💡 Example with catalog: dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/", err=True)
            click.echo("💡 Example with database: dbt-cube-sync dbt-to-cube -m manifest.json -s postgresql://user:pass@host:port/db -o output/", err=True)
            sys.exit(1)

        # Parse model filter if provided
        model_filter = None
        if models:
            model_filter = [m.strip() for m in models.split(',')]
            click.echo(f"🎯 Filtering models: {', '.join(model_filter)}")

        click.echo("🔄 Parsing dbt manifest...")
        parser = DbtParser(
            manifest_path=manifest,
            catalog_path=catalog,
            sqlalchemy_uri=sqlalchemy_uri,
            model_filter=model_filter
        )
        parsed_models = parser.parse_models()

        click.echo(f"📊 Found {len(parsed_models)} dbt models")

        if len(parsed_models) == 0:
            click.echo("⚠️  No models found. Make sure your models have both columns and metrics defined.")
            sys.exit(0)

        click.echo("🏗️  Generating Cube.js schemas...")
        generator = CubeGenerator(template_dir, output)
        generated_files = generator.generate_cube_files(parsed_models)

        click.echo(f"✅ Generated {len(generated_files)} Cube.js files:")
        for file_path in generated_files:
            click.echo(f"   • {file_path}")

    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


@main.command()
@click.argument('bi_tool', type=click.Choice(['superset', 'tableau', 'powerbi']))
@click.option('--cube-files', '-c',
              required=True,
              help='Directory containing Cube.js metric files')
@click.option('--url', '-u',
              required=True,
              help='BI tool URL (e.g., http://localhost:8088)')
@click.option('--username', '-n',
              required=True,
              help='BI tool username')
@click.option('--password', '-p',
              required=True,
              help='BI tool password')
@click.option('--cube-connection-name', '-d',
              default='Cube',
              help='Name of the Cube database connection in the BI tool (default: Cube)')
def cube_to_bi(bi_tool: str, cube_files: str, url: str, username: str, password: str, cube_connection_name: str):
    """Sync Cube.js schemas to BI tool datasets"""
    try:
        click.echo(f"🔄 Connecting to {bi_tool.title()} at {url}...")
        
        # Create connector config from command line params
        connector_config = {
            'url': url,
            'username': username,
            'password': password,
            'database_name': cube_connection_name
        }
        
        connector_instance = ConnectorRegistry.get_connector(bi_tool, **connector_config)
        
        click.echo(f"📊 Syncing Cube.js schemas to {bi_tool.title()}...")
        results = connector_instance.sync_cube_schemas(cube_files)
        
        successful = sum(1 for r in results if r.status == 'success')
        failed = sum(1 for r in results if r.status == 'failed')
        
        click.echo(f"✅ Sync complete: {successful} successful, {failed} failed")
        
        # Show detailed results
        for result in results:
            status_emoji = "✅" if result.status == 'success' else "❌"
            click.echo(f"   {status_emoji} {result.file_or_dataset}: {result.message}")
            
    except Exception as e:
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)



@main.command()
def version():
    """Show version information"""
    from . import __version__
    click.echo(f"dbt-cube-sync version {__version__}")


if __name__ == '__main__':
    main()