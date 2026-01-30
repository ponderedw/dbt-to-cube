"""
CLI interface for dbt-cube-sync tool
"""
import click
import os
import sys
from pathlib import Path
from typing import Optional

from .core.dbt_parser import DbtParser
from .core.cube_generator import CubeGenerator
from .core.state_manager import StateManager
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
@click.option('--state-path',
              required=False,
              default='.dbt-cube-sync-state.json',
              help='Path to state file for incremental sync (default: .dbt-cube-sync-state.json)')
@click.option('--force-full-sync',
              is_flag=True,
              default=False,
              help='Force full regeneration, ignore cached state')
@click.option('--no-state',
              is_flag=True,
              default=False,
              help='Disable state tracking (legacy behavior)')
def dbt_to_cube(
    manifest: str,
    catalog: Optional[str],
    sqlalchemy_uri: Optional[str],
    models: Optional[str],
    output: str,
    template_dir: str,
    state_path: str,
    force_full_sync: bool,
    no_state: bool
):
    """Generate Cube.js schemas from dbt models"""
    try:
        # Validate that at least one source of column types is provided
        if not catalog and not sqlalchemy_uri:
            click.echo("Error: You must provide either --catalog or --sqlalchemy-uri to get column data types", err=True)
            click.echo("Example with catalog: dbt-cube-sync dbt-to-cube -m manifest.json -c catalog.json -o output/", err=True)
            click.echo("Example with database: dbt-cube-sync dbt-to-cube -m manifest.json -s postgresql://user:pass@host:port/db -o output/", err=True)
            sys.exit(1)

        # Parse model filter if provided
        model_filter = None
        if models:
            model_filter = [m.strip() for m in models.split(',')]
            click.echo(f"Filtering models: {', '.join(model_filter)}")

        # Initialize state manager (if enabled)
        state_manager = None
        previous_state = None
        use_incremental = not no_state and not force_full_sync

        if not no_state:
            state_manager = StateManager(state_path)
            if not force_full_sync:
                previous_state = state_manager.load_state()
                if previous_state:
                    click.echo(f"Loaded previous state from {state_path}")

        click.echo("Parsing dbt manifest...")
        parser = DbtParser(
            manifest_path=manifest,
            catalog_path=catalog,
            sqlalchemy_uri=sqlalchemy_uri,
            model_filter=model_filter
        )

        # Get all manifest nodes with metrics (for checksum comparison)
        manifest_nodes = parser.get_manifest_nodes_with_metrics()
        click.echo(f"Found {len(manifest_nodes)} models with metrics in manifest")

        # Determine which models need regeneration
        if use_incremental and previous_state:
            added, modified, removed = state_manager.get_changed_models(
                manifest_nodes, previous_state
            )

            if not added and not modified and not removed:
                click.echo("No changes detected. All models are up to date.")
                sys.exit(0)

            click.echo(f"Incremental sync: {len(added)} added, {len(modified)} modified, {len(removed)} removed")

            # Clean up files for removed models
            if removed:
                files_to_delete = state_manager.get_files_to_delete(previous_state, removed)
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                        click.echo(f"  Deleted: {Path(file_path).name}")
                    except OSError as e:
                        click.echo(f"  Warning: Could not delete {file_path}: {e}")

            # Only parse changed models
            node_ids_to_process = list(added | modified)
            if not node_ids_to_process:
                # Only removals, no models to regenerate
                if state_manager:
                    new_state = state_manager.merge_state(
                        previous_state, manifest, manifest_nodes, {}, removed
                    )
                    state_manager.save_state(new_state)
                    click.echo(f"State saved to {state_path}")
                click.echo("Sync complete (only removals)")
                sys.exit(0)

            parsed_models = parser.parse_models(node_ids_filter=node_ids_to_process)
        else:
            # Full sync - parse all models
            if force_full_sync:
                click.echo("Forcing full sync...")
            parsed_models = parser.parse_models()

        click.echo(f"Processing {len(parsed_models)} dbt models")

        if len(parsed_models) == 0:
            click.echo("No models found. Make sure your models have both columns and metrics defined.")
            sys.exit(0)

        click.echo("Generating Cube.js schemas...")
        generator = CubeGenerator(template_dir, output)
        generated_files = generator.generate_cube_files(parsed_models)

        click.echo(f"Generated {len(generated_files)} Cube.js files:")
        for node_id, file_path in generated_files.items():
            click.echo(f"   {file_path}")

        # Save state (if enabled)
        if state_manager:
            if use_incremental and previous_state:
                # Merge with previous state
                removed_ids = removed if 'removed' in dir() else set()
                new_state = state_manager.merge_state(
                    previous_state, manifest, manifest_nodes, generated_files, removed_ids
                )
            else:
                # Create fresh state
                new_state = state_manager.create_state_from_results(
                    manifest, manifest_nodes, generated_files
                )
            state_manager.save_state(new_state)
            click.echo(f"State saved to {state_path}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
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


@main.command()
@click.option('--manifest', '-m',
              required=True,
              help='Path to dbt manifest.json file')
@click.option('--catalog', '-c',
              required=False,
              default=None,
              help='Path to dbt catalog.json file')
@click.option('--sqlalchemy-uri', '-s',
              required=False,
              default=None,
              help='SQLAlchemy database URI for fetching column types')
@click.option('--output', '-o',
              required=True,
              help='Output directory for Cube.js files')
@click.option('--state-path',
              required=False,
              default='.dbt-cube-sync-state.json',
              help='Path to state file for incremental sync')
@click.option('--force-full-sync',
              is_flag=True,
              default=False,
              help='Force full regeneration, ignore cached state')
@click.option('--superset-url',
              required=False,
              default=None,
              help='Superset URL (e.g., http://localhost:8088)')
@click.option('--superset-username',
              required=False,
              default=None,
              help='Superset username')
@click.option('--superset-password',
              required=False,
              default=None,
              help='Superset password')
@click.option('--cube-connection-name',
              default='Cube',
              help='Name of Cube database connection in Superset')
@click.option('--rag-api-url',
              required=False,
              default=None,
              help='RAG API URL for embedding updates (e.g., http://localhost:8000)')
def sync_all(
    manifest: str,
    catalog: Optional[str],
    sqlalchemy_uri: Optional[str],
    output: str,
    state_path: str,
    force_full_sync: bool,
    superset_url: Optional[str],
    superset_username: Optional[str],
    superset_password: Optional[str],
    cube_connection_name: str,
    rag_api_url: Optional[str]
):
    """
    Ultimate sync command: dbt → Cube.js → BI tools → RAG embeddings.

    Incrementally syncs everything based on state file. Only processes
    models that have changed since last sync.

    Examples:

      # Basic incremental sync (Cube.js only)
      dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output

      # Full pipeline with Superset
      dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output \\
        --superset-url http://localhost:8088 --superset-username admin --superset-password admin

      # Full pipeline with Superset + RAG embeddings
      dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output \\
        --superset-url http://localhost:8088 --superset-username admin --superset-password admin \\
        --rag-api-url http://localhost:8000

      # Force full rebuild
      dbt-cube-sync sync-all -m manifest.json -c catalog.json -o ./cube_output --force-full-sync
    """
    import requests

    try:
        # Validate that at least one source of column types is provided
        if not catalog and not sqlalchemy_uri:
            click.echo("Error: You must provide either --catalog or --sqlalchemy-uri", err=True)
            sys.exit(1)

        click.echo("=" * 60)
        click.echo("SYNC-ALL: Incremental Pipeline")
        click.echo("=" * 60)

        # Track what changed for downstream updates
        changes_detected = False
        added_models = set()
        modified_models = set()
        removed_models = set()

        # Initialize state manager and load previous state
        state_manager = StateManager(state_path)
        previous_state = None
        current_state = None

        if not force_full_sync:
            previous_state = state_manager.load_state()
            if previous_state:
                click.echo(f"  Loaded state from {state_path}")

        # ============================================================
        # STEP 1: Incremental dbt → Cube.js sync
        # ============================================================
        click.echo("\n[1/3] dbt → Cube.js schemas")
        click.echo("-" * 40)

        # Parse manifest
        parser = DbtParser(
            manifest_path=manifest,
            catalog_path=catalog,
            sqlalchemy_uri=sqlalchemy_uri
        )

        manifest_nodes = parser.get_manifest_nodes_with_metrics()
        click.echo(f"  Found {len(manifest_nodes)} models with metrics")

        # Determine what changed
        if not force_full_sync and previous_state:
            added_models, modified_models, removed_models = state_manager.get_changed_models(
                manifest_nodes, previous_state
            )

            if not added_models and not modified_models and not removed_models:
                click.echo("  No changes detected - all models up to date")
            else:
                changes_detected = True
                click.echo(f"  Changes: {len(added_models)} added, {len(modified_models)} modified, {len(removed_models)} removed")

                # Clean up removed model files
                if removed_models:
                    files_to_delete = state_manager.get_files_to_delete(previous_state, removed_models)
                    for file_path in files_to_delete:
                        try:
                            os.remove(file_path)
                            click.echo(f"    Deleted: {Path(file_path).name}")
                        except OSError:
                            pass

            node_ids_to_process = list(added_models | modified_models)
        else:
            # Force full sync
            changes_detected = True
            added_models = set(manifest_nodes.keys())
            node_ids_to_process = list(manifest_nodes.keys())
            click.echo(f"  Full sync: processing all {len(node_ids_to_process)} models")

        # Generate Cube.js files for changed models
        generated_files = {}
        cube_sync_error = None
        try:
            if node_ids_to_process:
                parsed_models = parser.parse_models(node_ids_filter=node_ids_to_process)

                if parsed_models:
                    generator = CubeGenerator('./cube/templates', output)
                    generated_files = generator.generate_cube_files(parsed_models)
                    click.echo(f"  Generated {len(generated_files)} Cube.js files")
        except Exception as e:
            cube_sync_error = str(e)
            click.echo(f"  Error: {cube_sync_error}", err=True)

        # Build/update state
        if changes_detected or force_full_sync:
            if previous_state and not force_full_sync:
                current_state = state_manager.merge_state(
                    previous_state, manifest, manifest_nodes, generated_files, removed_models
                )
            else:
                current_state = state_manager.create_state_from_results(
                    manifest, manifest_nodes, generated_files
                )
        else:
            # No changes - use previous state or create empty one
            current_state = previous_state or state_manager.create_state_from_results(
                manifest, manifest_nodes, {}
            )

        # Save cube sync state
        state_manager.save_state(current_state)
        click.echo(f"  State saved to {state_path}")

        if cube_sync_error:
            click.echo(f"  Error during cube generation: {cube_sync_error}", err=True)

        # Build a mapping from model name (file stem) to node_id for status updates
        model_name_to_node_id = {}
        for node_id in current_state.models.keys():
            # Extract model name from output file (e.g., "model/cubes/ModelName.js" -> "ModelName")
            output_file = current_state.models[node_id].output_file
            model_name = Path(output_file).stem
            model_name_to_node_id[model_name] = node_id

        # ============================================================
        # STEP 2: Sync to Superset (if configured)
        # ============================================================
        click.echo("\n[2/3] Cube.js → Superset")
        click.echo("-" * 40)

        if not superset_url or not superset_username or not superset_password:
            click.echo("  Skipped - no Superset credentials provided")
        else:
            # Get models that need Superset sync (status is None or 'failed')
            models_to_sync_ids = state_manager.get_models_needing_sync(current_state, 'superset')

            if not models_to_sync_ids and not force_full_sync:
                click.echo("  Skipped - all models already synced successfully")
            else:
                # Convert node_ids to model names for filtering
                models_to_sync_names = set()
                for node_id in models_to_sync_ids:
                    if node_id in current_state.models:
                        output_file = current_state.models[node_id].output_file
                        model_name = Path(output_file).stem
                        models_to_sync_names.add(model_name)

                try:
                    connector_config = {
                        'url': superset_url,
                        'username': superset_username,
                        'password': superset_password,
                        'database_name': cube_connection_name
                    }

                    connector = ConnectorRegistry.get_connector('superset', **connector_config)

                    if force_full_sync:
                        results = connector.sync_cube_schemas(output)
                    else:
                        results = connector.sync_cube_schemas(output, models_to_sync_names)

                    # Update per-model status
                    for r in results:
                        model_name = r.file_or_dataset.replace('.js', '')
                        node_id = model_name_to_node_id.get(model_name)
                        if node_id:
                            state_manager.update_model_sync_status(
                                current_state, node_id, 'superset',
                                'success' if r.status == 'success' else 'failed'
                            )

                    successful = sum(1 for r in results if r.status == 'success')
                    failed = sum(1 for r in results if r.status == 'failed')
                    click.echo(f"  Synced: {successful} successful, {failed} failed")

                except Exception as e:
                    click.echo(f"  Error: {str(e)}", err=True)
                    # Mark all models we tried to sync as failed
                    for node_id in models_to_sync_ids:
                        state_manager.update_model_sync_status(
                            current_state, node_id, 'superset', 'failed'
                        )

                state_manager.save_state(current_state)

        # ============================================================
        # STEP 3: Update RAG embeddings (if configured)
        # ============================================================
        click.echo("\n[3/3] Update RAG embeddings")
        click.echo("-" * 40)

        if not rag_api_url:
            click.echo("  Skipped - no RAG API URL provided")
        else:
            # Get models that need RAG sync (status is None or 'failed')
            models_to_embed_ids = state_manager.get_models_needing_sync(current_state, 'rag')

            if not models_to_embed_ids and not force_full_sync:
                click.echo("  Skipped - all models already synced successfully")
            else:
                if force_full_sync:
                    models_to_embed_ids = set(current_state.models.keys())

                try:
                    # Call the RAG API to re-ingest embeddings
                    response = requests.post(
                        f"{rag_api_url.rstrip('/')}/embeddings/ingest",
                        json={"schema_dir": output},
                        timeout=120
                    )

                    if response.status_code == 200:
                        result = response.json()
                        click.echo(f"  Ingested {result.get('schemas_ingested', 0)} schema documents")
                        # Mark all models as succeeded
                        for node_id in models_to_embed_ids:
                            state_manager.update_model_sync_status(
                                current_state, node_id, 'rag', 'success'
                            )
                    else:
                        click.echo(f"  Error: RAG API returned {response.status_code}", err=True)
                        # Mark all models as failed
                        for node_id in models_to_embed_ids:
                            state_manager.update_model_sync_status(
                                current_state, node_id, 'rag', 'failed'
                            )
                except requests.RequestException as e:
                    click.echo(f"  Error: Could not reach RAG API: {e}", err=True)
                    # Mark all models as failed
                    for node_id in models_to_embed_ids:
                        state_manager.update_model_sync_status(
                            current_state, node_id, 'rag', 'failed'
                        )

                state_manager.save_state(current_state)

        # ============================================================
        # Summary
        # ============================================================
        click.echo("\n" + "=" * 60)
        click.echo("SYNC COMPLETE")
        click.echo("=" * 60)

        # Get per-model sync summaries
        superset_summary = state_manager.get_sync_summary(current_state, 'superset')
        rag_summary = state_manager.get_sync_summary(current_state, 'rag')

        def format_summary(summary, step_configured):
            if not step_configured:
                return "skipped (not configured)"
            if summary['failed'] > 0:
                return f"{summary['success']} success, {summary['failed']} failed (will retry)"
            elif summary['pending'] > 0:
                return f"{summary['success']} success, {summary['pending']} pending"
            else:
                return f"{summary['success']} success"

        click.echo(f"  Cube.js files: {len(current_state.models)} models")
        click.echo(f"  Superset sync: {format_summary(superset_summary, superset_url)}")
        click.echo(f"  RAG sync:      {format_summary(rag_summary, rag_api_url)}")

        if changes_detected or force_full_sync:
            click.echo(f"  Models processed: {len(added_models) + len(modified_models)}")
            click.echo(f"  Models removed: {len(removed_models)}")
            click.echo(f"  Cube.js files generated: {len(generated_files)}")
        else:
            click.echo("  No model changes detected")

        # Exit with error if any models failed
        any_failed = superset_summary['failed'] > 0 or rag_summary['failed'] > 0
        if any_failed:
            click.echo("\n  ⚠️  Some models failed - they will be retried on next run")
            sys.exit(1)

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()