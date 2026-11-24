"""
CLI interface for dbt-cube-sync tool
"""
import click
import os
import sys
import datetime
import time
import yaml
import requests as _requests
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .core.dbt_parser import DbtParser
from .core.cube_generator import CubeGenerator
from .core.state_manager import StateManager
from .connectors.base import ConnectorRegistry
from .config import Config
from .cube_auth import cube_auth_headers

# Import connectors to register them
from .connectors import superset, tableau, powerbi


def _load_deployed_file_hashes(
    s3_bucket: Optional[str] = None,
    s3_prefix: str = 'cubes',
    deployed_dir: Optional[str] = None,
) -> Dict[str, str]:
    """Return {filename: sha256_hex} for all .yaml files in the deployed state.

    Pass either s3_bucket (reads from S3) or deployed_dir (reads from disk).
    """
    import hashlib

    hashes: Dict[str, str] = {}

    if s3_bucket:
        try:
            import boto3
        except ImportError:
            raise click.ClickException("boto3 required: pip install boto3")
        s3 = boto3.client('s3')
        prefix = s3_prefix.rstrip('/') + '/'
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key.endswith('.yaml'):
                    filename = Path(key).name
                    content = s3.get_object(Bucket=s3_bucket, Key=key)['Body'].read()
                    hashes[filename] = hashlib.sha256(content).hexdigest()
    elif deployed_dir:
        for yaml_file in Path(deployed_dir).glob('*.yaml'):
            hashes[yaml_file.name] = hashlib.sha256(yaml_file.read_bytes()).hexdigest()

    return hashes


def _diff_cube_files(
    generated_dir: str,
    deployed_hashes: Dict[str, str],
) -> tuple:
    """Compare generated cube files against deployed hashes.

    Returns (added, modified, removed) — sets of cube name strings (no .yaml extension).
    """
    import hashlib

    generated: Dict[str, str] = {}
    for yaml_file in Path(generated_dir).glob('*.yaml'):
        generated[yaml_file.name] = hashlib.sha256(yaml_file.read_bytes()).hexdigest()

    gen_names = set(generated)
    dep_names = set(deployed_hashes)

    added = {f[:-5] for f in gen_names - dep_names}      # in new, not in deployed
    removed = {f[:-5] for f in dep_names - gen_names}    # in deployed, not in new
    modified = {
        f[:-5] for f in gen_names & dep_names
        if generated[f] != deployed_hashes[f]
    }
    return added, modified, removed



def _fetch_cube_api_meta(cube_api_url: str, cube_api_secret: str = '') -> Dict[str, dict]:
    """Return {cube_name: cube_info} from the Cube.js /meta API."""
    url = cube_api_url.rstrip('/') + '/cubejs-api/v1/meta'
    headers = cube_auth_headers(cube_api_secret)
    resp = _requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return {c['name']: c for c in resp.json().get('cubes', [])}


def _diff_api_states(
    old_meta: Dict[str, dict],
    new_meta: Dict[str, dict],
) -> Tuple[Set[str], Set[str], Set[str], Dict[str, List[str]]]:
    """Compare two Cube.js /meta snapshots (old vs new deployed state).

    Returns (added, modified, removed, diffs):
    - added:    cube names in new_meta but not old_meta
    - modified: cube names in both with structural differences
    - removed:  cube names in old_meta but not new_meta
    - diffs:    {cube_name: [human-readable diff lines]}

    Dimension types ARE compared (both sides use the same /meta convention).
    Measure types are NOT compared — /meta returns "number" for all aggregates.
    """
    added = set(new_meta) - set(old_meta)
    removed = set(old_meta) - set(new_meta)
    modified: Set[str] = set()
    diffs: Dict[str, List[str]] = {}

    for name in set(old_meta) & set(new_meta):
        old = old_meta[name]
        new = new_meta[name]

        old_dims = {d['name'].split('.')[-1]: d.get('type', 'string') for d in old.get('dimensions', [])}
        new_dims = {d['name'].split('.')[-1]: d.get('type', 'string') for d in new.get('dimensions', [])}

        # Measure names only — /meta returns "number" for all aggregation types
        old_meas = {m['name'].split('.')[-1] for m in old.get('measures', [])}
        new_meas = {m['name'].split('.')[-1] for m in new.get('measures', [])}

        cube_diffs: List[str] = []

        for d in sorted(new_dims.keys() - old_dims.keys()):
            cube_diffs.append(f"    + dimension {d} ({new_dims[d]})")
        for d in sorted(old_dims.keys() - new_dims.keys()):
            cube_diffs.append(f"    - dimension {d} ({old_dims[d]})")
        for d in sorted(old_dims.keys() & new_dims.keys()):
            if old_dims[d] != new_dims[d]:
                cube_diffs.append(f"    ~ dimension {d}: {old_dims[d]} → {new_dims[d]}")

        for m in sorted(new_meas - old_meas):
            cube_diffs.append(f"    + measure {m}")
        for m in sorted(old_meas - new_meas):
            cube_diffs.append(f"    - measure {m}")

        if cube_diffs:
            modified.add(name)
            diffs[name] = cube_diffs

    return added, modified, removed, diffs


def _diff_yaml_states(
    old_yaml: Dict[str, dict],
    new_yaml: Dict[str, dict],
) -> Dict[str, List[str]]:
    """Diff pre-aggregations and access policies between two YAML cube states.

    Returns {cube_name: [diff lines]} for cubes with pre-agg or policy changes.
    /meta does not expose pre-aggregations or access policies, so YAML is the
    only source of truth for these.
    """
    all_names = set(old_yaml) | set(new_yaml)
    result: Dict[str, List[str]] = {}

    for name in sorted(all_names):
        old = old_yaml.get(name, {})
        new = new_yaml.get(name, {})
        lines: List[str] = []

        # Pre-aggregations
        old_pas = {pa['name']: pa for pa in old.get('pre_aggregations', [])}
        new_pas = {pa['name']: pa for pa in new.get('pre_aggregations', [])}
        for pa_name in sorted(new_pas.keys() - old_pas.keys()):
            lines.append(f"    + pre_aggregation {pa_name} ({new_pas[pa_name].get('type', '?')})")
        for pa_name in sorted(old_pas.keys() - new_pas.keys()):
            lines.append(f"    - pre_aggregation {pa_name} ({old_pas[pa_name].get('type', '?')})")
        for pa_name in sorted(old_pas.keys() & new_pas.keys()):
            if old_pas[pa_name] != new_pas[pa_name]:
                lines.append(f"    ~ pre_aggregation {pa_name} changed")

        # Access policies
        def _policy_key(p: dict, i: int) -> str:
            return p.get('group') or p.get('groups', [str(i)])[0] if isinstance(p.get('groups'), list) else str(i)
        old_groups = {_policy_key(p, i) for i, p in enumerate(old.get('access_policy', []))}
        new_groups = {_policy_key(p, i) for i, p in enumerate(new.get('access_policy', []))}
        for g in sorted(new_groups - old_groups):
            lines.append(f"    + access_policy group={g}")
        for g in sorted(old_groups - new_groups):
            lines.append(f"    - access_policy group={g}")

        if lines:
            result[name] = lines

    return result


def _post_cube_query(
    payload: dict,
    cube_api_url: str,
    headers: dict,
) -> Tuple[bool, str]:
    """POST a Cube.js /load query and return (ok, detail_or_error)."""
    url = cube_api_url.rstrip('/') + '/cubejs-api/v1/load'
    for _ in range(10):
        try:
            resp = _requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                body = resp.json()
                error = body.get('error', '')
                if error == 'Continue wait':
                    click.echo('.', nl=False)
                    time.sleep(5)
                    continue
                if error:
                    return False, error
                return True, str(len(body.get('data', [])))
            try:
                err = resp.json().get('error', resp.text[:200])
            except Exception:
                err = resp.text[:200]
            return False, err
        except Exception as e:
            return False, str(e)
    return False, 'max retries exceeded'



def _query_cube_via_api(
    cube_name: str,
    cube_info: dict,
    cube_api_url: str,
    cube_api_secret: str = '',
) -> Tuple[bool, str]:
    """Validate a cube with a single query covering all measures and dimensions."""
    measures = [m['name'] for m in cube_info.get('measures', [])]
    if not measures:
        return True, 'no measures (skipped)'

    headers = {'Content-Type': 'application/json', **cube_auth_headers(cube_api_secret)}

    def _full(name: str) -> str:
        return name if '.' in name else f'{cube_name}.{name}'

    all_measures = [_full(m) for m in measures]
    plain_dims   = [_full(d['name']) for d in cube_info.get('dimensions', []) if d.get('type') != 'time']
    time_dims    = [{'dimension': _full(d['name']), 'granularity': 'day'}
                    for d in cube_info.get('dimensions', []) if d.get('type') == 'time']

    n_m = len(all_measures)
    n_d = len(plain_dims) + len(time_dims)
    click.echo(f"\n  {cube_name}  ({n_m} measure(s), {n_d} dim(s))")

    q: dict = {'measures': all_measures, 'limit': 1}
    if plain_dims:
        q['dimensions'] = plain_dims
    if time_dims:
        q['timeDimensions'] = time_dims

    click.echo('  Started querying ', nl=False)
    ok, detail = _post_cube_query({'query': q}, cube_api_url, headers)
    if ok:
        click.echo('  succeeded')
        return True, f'1 row(s), {n_m} measure(s), {n_d} dim(s)'
    else:
        click.echo(f'  error: {detail}')
        return False, detail


def _upload_to_s3(output_dir: str, s3_bucket: str, s3_prefix: str) -> str:
    """Upload generated Cube.js files to S3 and return the version string.

    Requires boto3 (pip install boto3).  AWS credentials are resolved via the
    standard boto3 chain (env vars, ~/.aws/credentials, IAM role, etc.).

    Returns the schema version string written to S3.
    """
    try:
        import boto3
    except ImportError:
        raise click.ClickException(
            "boto3 is required for S3 upload. Install it with: pip install boto3"
        )

    s3 = boto3.client('s3')
    prefix = s3_prefix.rstrip('/') + '/' if s3_prefix else ''

    output_path = Path(output_dir)
    uploaded = 0
    for yaml_file in output_path.glob('*.yaml'):
        s3_key = f"{prefix}{yaml_file.name}"
        s3.upload_file(str(yaml_file), s3_bucket, s3_key)
        uploaded += 1

    version = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    s3.put_object(
        Bucket=s3_bucket,
        Key=f"{prefix}.schema-version",
        Body=version.encode(),
        ContentType='text/plain',
    )

    click.echo(f"  Uploaded {uploaded} cube file(s) to s3://{s3_bucket}/{prefix}")
    click.echo(f"  Schema version: {version}")
    return version


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
@click.option('--ci-mode',
              is_flag=True,
              default=False,
              help='CI mode: skip output file existence checks (for environments where output files do not exist locally)')
def dbt_to_cube(
    manifest: str,
    catalog: Optional[str],
    sqlalchemy_uri: Optional[str],
    models: Optional[str],
    output: str,
    template_dir: str,
    state_path: str,
    force_full_sync: bool,
    no_state: bool,
    ci_mode: bool,
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
            model_filter=model_filter,
        )

        # Get all manifest nodes with metrics (for checksum comparison)
        manifest_nodes = parser.get_manifest_nodes_with_metrics()
        # Include MetricFlow semantic model stubs so they are never flagged as removed
        manifest_nodes.update(parser.get_manifest_semantic_model_nodes())
        click.echo(f"Found {len(manifest_nodes)} models with metrics in manifest")

        # Handle removed models (dbt checksum still used to detect removals)
        removed = set()
        if use_incremental and previous_state:
            _, _, removed = state_manager.get_changed_models(
                manifest_nodes, previous_state, check_output_files=False
            )
            if removed:
                files_to_delete = state_manager.get_files_to_delete(previous_state, removed)
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                        click.echo(f"  Deleted: {Path(file_path).name}")
                    except OSError as e:
                        click.echo(f"  Warning: Could not delete {file_path}: {e}")

        # Always parse and generate all models — output checksum decides what changed
        parsed_models = parser.parse_models()

        # Also include MetricFlow semantic models (if any)
        mf_models = parser.parse_metricflow_models()
        mf_views = parser.parse_metricflow_views()
        if mf_models:
            click.echo(f"Found {len(mf_models)} MetricFlow semantic model(s)")
            # Avoid duplicates (model names already present via config.meta.metrics)
            existing_names = {m.name for m in parsed_models}
            parsed_models += [m for m in mf_models if m.name not in existing_names]

        click.echo(f"Processing {len(parsed_models)} dbt models")

        if len(parsed_models) == 0:
            click.echo("No models found. Make sure your models have both columns and metrics defined.")
            sys.exit(0)

        # Pass stored output checksums so unchanged files are not overwritten
        stored_checksums = {}
        if previous_state:
            stored_checksums = {
                nid: m.output_checksum
                for nid, m in previous_state.models.items()
                if m.output_checksum
            }

        # Remove any legacy .js files left over from older schema format
        output_path = Path(output)
        for js_file in output_path.glob('*.js'):
            js_file.unlink()
            click.echo(f"  Removed legacy file: {js_file.name}")

        click.echo("Generating Cube.js schemas...")
        generator = CubeGenerator(template_dir, output)
        file_paths, output_checksums, changed_ids = generator.generate_cube_files(
            parsed_models, stored_checksums=stored_checksums
        )
        view_paths = generator.generate_view_files(mf_views)
        if view_paths:
            click.echo(f"Generated {len(view_paths)} cross-model view(s)")

        click.echo(f"Processed {len(file_paths)} Cube.js files ({len(changed_ids)} changed):")
        for node_id, fp in file_paths.items():
            click.echo(f"   {fp}")

        # Save state (if enabled)
        if state_manager:
            if use_incremental and previous_state:
                new_state = state_manager.merge_state(
                    previous_state, manifest, manifest_nodes, file_paths, removed,
                    output_checksums=output_checksums, changed_node_ids=changed_ids,
                )
            else:
                new_state = state_manager.create_state_from_results(
                    manifest, manifest_nodes, file_paths, output_checksums=output_checksums
                )
            state_manager.save_state(new_state)
            click.echo(f"State saved to {state_path}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


@main.command()
@click.argument('bi_tool', type=click.Choice(['superset', 'tableau', 'powerbi']))
@click.option('--url', '-u', required=True,
              help='BI tool base URL (e.g., http://localhost:8088)')
@click.option('--username', '-n', required=True, help='BI tool username')
@click.option('--password', '-p', required=True, help='BI tool password')
@click.option('--cube-connection-name', '-d', default='Cube',
              help='Name of the Cube database connection in the BI tool (default: Cube)')
# ── API-to-API mode (recommended) ────────────────────────────────────────────
@click.option('--cube-api-url',
              required=False, default=None,
              envvar='CUBEJS_API_URL',
              help='Cube.js API base URL (e.g., http://cube:4000). '
                   'When set, fetches cube definitions directly from Cube API — '
                   'no local files needed.  Creates, updates, and removes Superset '
                   'datasets to match the live Cube.js state.')
@click.option('--cube-api-secret',
              required=False, default='',
              envvar='CUBEJS_API_SECRET',
              help='Cube.js API secret (passed as Bearer token)')
# ── File-based mode (legacy) ──────────────────────────────────────────────────
@click.option('--cube-files', '-c',
              required=False, default=None,
              help='Directory of local .js cube files (legacy mode; '
                   'prefer --cube-api-url for API-to-API sync)')
def cube_to_bi(
    bi_tool: str,
    url: str,
    username: str,
    password: str,
    cube_connection_name: str,
    cube_api_url: Optional[str],
    cube_api_secret: str,
    cube_files: Optional[str],
):
    """Sync Cube.js schemas to BI tool datasets.

    API-TO-API MODE (recommended):

      Fetches cube definitions directly from the Cube.js API, then creates,
      updates, and deletes Superset datasets to match.  No local files needed.

        dbt-cube-sync cube-to-bi superset \\
          --cube-api-url http://cube:4000 \\
          --cube-api-secret $CUBEJS_API_SECRET \\
          --url http://superset:8088 \\
          --username admin --password admin

    FILE MODE (legacy):

        dbt-cube-sync cube-to-bi superset --cube-files ./model/cubes ...
    """
    if not cube_api_url and not cube_files:
        raise click.UsageError(
            "Provide --cube-api-url (API-to-API mode) or --cube-files (legacy file mode)."
        )

    try:
        click.echo("=" * 62)
        click.echo(f"CUBE-TO-BI: {bi_tool.upper()}")
        click.echo("=" * 62)

        connector = ConnectorRegistry.get_connector(
            bi_tool,
            url=url,
            username=username,
            password=password,
            database_name=cube_connection_name,
        )

        if cube_api_url:
            click.echo(f"\nMode: API-to-API  ({cube_api_url} → {url})")
            results, _ = connector.sync_from_cube_api(
                cube_api_url=cube_api_url,
                cube_api_secret=cube_api_secret,
            )
        else:
            click.echo(f"\nMode: file-based  ({cube_files} → {url})")
            results = connector.sync_cube_schemas(cube_files)

        ok = sum(1 for r in results if r.status == 'success')
        fail = sum(1 for r in results if r.status == 'failed')
        click.echo(f"\n{ok} succeeded, {fail} failed")
        if fail:
            sys.exit(1)

    except click.UsageError:
        raise
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)



@main.command()
def version():
    """Show version information"""
    from . import __version__
    click.echo(f"dbt-cube-sync version {__version__}")


@main.command()
@click.option('--manifest', '-m', required=True,
              help='Path to dbt manifest.json')
@click.option('--sqlalchemy-uri', '-s', required=False, default=None,
              help='DB URI for column type resolution (required when using --s3-bucket / --deployed-dir)')
@click.option('--catalog', '-c', required=False, default=None,
              help='Path to dbt catalog.json (alternative to --sqlalchemy-uri)')
# ── File-based comparison (new) ───────────────────────────────────────────────
@click.option('--s3-bucket', required=False, default=None,
              envvar='CUBEJS_SCHEMA_S3_BUCKET',
              help='Compare generated cube files against files in this S3 bucket')
@click.option('--s3-prefix', required=False, default='cubes',
              envvar='CUBEJS_SCHEMA_S3_PREFIX',
              help='S3 key prefix (default: cubes)')
@click.option('--deployed-dir', required=False, default=None,
              help='Compare generated cube files against this local directory')
@click.option('--gen-output', required=False, default=None,
              help='Where to write generated cube files (default: temp dir)')
# ── Manifest-based comparison (legacy) ────────────────────────────────────────
@click.option('--state', required=False, default=None,
              help='Production state file (.dbt-cube-sync-state.json) — legacy mode')
# ── Common ────────────────────────────────────────────────────────────────────
@click.option('--output', '-o', required=False, default=None,
              help='Write results to this JSON file')
@click.option('--fail-on-changes', is_flag=True, default=False,
              help='Exit with code 2 if changes are detected')
def compare_state(
    manifest: str,
    sqlalchemy_uri: Optional[str],
    catalog: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: str,
    deployed_dir: Optional[str],
    gen_output: Optional[str],
    state: Optional[str],
    output: Optional[str],
    fail_on_changes: bool,
):
    """
    Detect which Cube.js schemas have changed.

    FILE-BASED MODE (recommended): pass --s3-bucket or --deployed-dir.
      Generates all cube files from the manifest and compares their content
      against the deployed state.  No state file needed — comparison is
      purely based on file content hashes.  Catches changes from both dbt
      model edits and template/generator code changes.

      dbt-cube-sync compare-state \\
        -m manifest.json -s $DB_URI \\
        --s3-bucket my-cube-bucket [--s3-prefix cubes]

    LEGACY MODE: pass --state (production state file).
      Compares dbt manifest checksums against a saved state file.

      dbt-cube-sync compare-state -m manifest.json --state prod_state.json

    Exit codes:  0 = no changes,  1 = error,  2 = changes (with --fail-on-changes)
    """
    import json
    import tempfile

    file_based = bool(s3_bucket or deployed_dir)

    try:
        click.echo("=" * 62)
        click.echo("COMPARE STATE")
        click.echo("=" * 62)

        if file_based:
            # ── File-based mode ────────────────────────────────────────
            if not sqlalchemy_uri and not catalog:
                raise click.UsageError(
                    "File-based comparison requires --sqlalchemy-uri or --catalog "
                    "to generate cube files for comparison."
                )

            click.echo(
                f"\nMode: file-based diff against "
                f"{'s3://' + s3_bucket + '/' + s3_prefix if s3_bucket else deployed_dir}"
            )

            # Generate cube files
            use_tmp = gen_output is None
            tmp_dir = None
            try:
                if use_tmp:
                    tmp_dir = tempfile.mkdtemp(prefix='dbt-cube-compare-')
                    cubes_dir = str(Path(tmp_dir) / 'cubes')
                else:
                    cubes_dir = gen_output

                Path(cubes_dir).mkdir(parents=True, exist_ok=True)

                click.echo("\nGenerating cube files...")
                parser = DbtParser(
                    manifest_path=manifest,
                    catalog_path=catalog,
                    sqlalchemy_uri=sqlalchemy_uri,
                )
                models = parser.parse_models()
                mf_models = parser.parse_metricflow_models()
                mf_views = parser.parse_metricflow_views()
                if mf_models:
                    existing = {m.name for m in models}
                    models += [m for m in mf_models if m.name not in existing]

                generator = CubeGenerator('./cube/templates', cubes_dir)
                file_paths, _, _ = generator.generate_cube_files(models)
                generator.generate_view_files(mf_views)
                click.echo(f"  Generated {len(file_paths)} cube file(s) + {len(mf_views)} view(s)")

                # Load deployed state
                click.echo("\nLoading deployed state...")
                deployed_hashes = _load_deployed_file_hashes(
                    s3_bucket=s3_bucket,
                    s3_prefix=s3_prefix,
                    deployed_dir=deployed_dir,
                )
                click.echo(f"  Found {len(deployed_hashes)} deployed file(s)")

                # Diff
                added, modified, removed = _diff_cube_files(cubes_dir, deployed_hashes)

            finally:
                if tmp_dir:
                    import shutil
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            has_changes = bool(added or modified or removed)
            result_extra: dict = {
                'generated_count': len(file_paths),
                'deployed_count': len(deployed_hashes),
            }

        else:
            # ── Legacy manifest-checksum mode ──────────────────────────
            if not state:
                raise click.UsageError(
                    "Provide --s3-bucket / --deployed-dir for file-based comparison, "
                    "or --state for legacy manifest-checksum comparison."
                )

            click.echo(f"\nMode: manifest checksum diff against {state}")
            click.echo(f"\nLoading manifest from {manifest}...")
            parser_tmp = DbtParser(manifest_path=manifest)
            manifest_nodes = parser_tmp.get_manifest_nodes_with_metrics()
            click.echo(f"  Found {len(manifest_nodes)} models with metrics")

            click.echo(f"\nLoading production state from {state}...")
            sm = StateManager(state)
            try:
                with open(state, 'r') as f:
                    state_data = json.load(f)
                from .core.models import SyncState
                prod_state = SyncState.model_validate(state_data) if state_data else None
                click.echo(f"  Found {len(prod_state.models) if prod_state else 0} models in state")
            except (FileNotFoundError, json.JSONDecodeError):
                prod_state = None
                click.echo("  No valid state found — treating all as new")

            if prod_state:
                added_raw, modified_raw, removed_raw = sm.get_changed_models(
                    manifest_nodes, prod_state, check_output_files=False
                )
                # Convert node IDs to cube names for consistent output
                added = {nid.split('.')[-1] for nid in added_raw}
                modified = {nid.split('.')[-1] for nid in modified_raw}
                removed = {nid.split('.')[-1] for nid in removed_raw}
            else:
                added = {nid.split('.')[-1] for nid in manifest_nodes}
                modified = set()
                removed = set()

            has_changes = bool(added or modified or removed)
            result_extra = {
                'manifest_model_count': len(manifest_nodes),
                'state_model_count': len(prod_state.models) if prod_state else 0,
            }

        # ── Print results ──────────────────────────────────────────────
        click.echo("\n" + "─" * 62)
        click.echo("CHANGE DETECTION RESULTS")
        click.echo("─" * 62)

        if added:
            click.echo(f"\n  + Added   ({len(added)}):")
            for name in sorted(added):
                click.echo(f"      {name}")
        if modified:
            click.echo(f"\n  ~ Changed ({len(modified)}):")
            for name in sorted(modified):
                click.echo(f"      {name}")
        if removed:
            click.echo(f"\n  - Removed ({len(removed)}):")
            for name in sorted(removed):
                click.echo(f"      {name}")
        if not has_changes:
            click.echo("\n  No changes detected")

        click.echo("\n" + "─" * 62)
        click.echo(
            f"  Added: {len(added)}  Changed: {len(modified)}  Removed: {len(removed)}"
        )
        click.echo("=" * 62)

        # ── Write JSON ─────────────────────────────────────────────────
        if output:
            result_json = {
                'has_changes': has_changes,
                'added': sorted(added),
                'modified': sorted(modified),
                'removed': sorted(removed),
                **result_extra,
            }
            with open(output, 'w') as f:
                json.dump(result_json, f, indent=2)
            click.echo(f"\nResults written to {output}")

        if has_changes and fail_on_changes:
            sys.exit(2)

    except click.UsageError:
        raise
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


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
@click.option('--cube-api-url',
              required=False,
              default=None,
              envvar='CUBEJS_API_URL',
              help='Cube.js API URL for Superset API-to-API sync (e.g. http://cube:4000)')
@click.option('--cube-api-secret',
              required=False,
              default='',
              envvar='CUBEJS_API_SECRET',
              help='Cube.js API secret (passed as Bearer token)')
@click.option('--rag-api-url',
              required=False,
              default=None,
              help='RAG API URL for embedding updates (e.g., http://localhost:8000)')
@click.option('--s3-bucket',
              required=False,
              default=None,
              envvar='CUBEJS_SCHEMA_S3_BUCKET',
              help='S3 bucket to push generated cube files to (enables remote schema sync)')
@click.option('--s3-prefix',
              required=False,
              default='cubes',
              envvar='CUBEJS_SCHEMA_S3_PREFIX',
              help='S3 key prefix for cube files (default: cubes)')
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
    cube_api_url: Optional[str],
    cube_api_secret: str,
    rag_api_url: Optional[str],
    s3_bucket: Optional[str],
    s3_prefix: str,
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
        manifest_nodes.update(parser.get_manifest_semantic_model_nodes())
        click.echo(f"  Found {len(manifest_nodes)} models with metrics")

        # Detect removed models and clean up their files
        removed_models = set()
        if not force_full_sync and previous_state:
            _, _, removed_models = state_manager.get_changed_models(
                manifest_nodes, previous_state, check_output_files=False
            )
            if removed_models:
                changes_detected = True
                files_to_delete = state_manager.get_files_to_delete(previous_state, removed_models)
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                        click.echo(f"    Deleted: {Path(file_path).name}")
                    except OSError:
                        pass

        # Remove stale .yaml files on force-full-sync
        if force_full_sync:
            output_path = Path(output)
            if output_path.exists():
                expected_stems = {
                    CubeGenerator._to_pascal_case(node_data.get("name", ""))
                    for node_data in manifest_nodes.values()
                }
                for stale_file in output_path.glob("*.yaml"):
                    if stale_file.stem not in expected_stems:
                        stale_file.unlink()

        # Always generate all models — output checksum decides what's actually new
        stored_checksums = {}
        if previous_state and not force_full_sync:
            stored_checksums = {
                nid: m.output_checksum
                for nid, m in previous_state.models.items()
                if m.output_checksum
            }

        file_paths: Dict[str, str] = {}
        output_checksums: Dict[str, str] = {}
        changed_ids: Set[str] = set()
        cube_sync_error = None
        parsed_models: list = []
        try:
            parsed_models = parser.parse_models()

            mf_models = parser.parse_metricflow_models()
            mf_views = parser.parse_metricflow_views()
            if mf_models:
                existing_names = {m.name for m in parsed_models}
                parsed_models += [m for m in mf_models if m.name not in existing_names]

            if parsed_models:
                generator = CubeGenerator('./cube/templates', output)
                file_paths, output_checksums, changed_ids = generator.generate_cube_files(
                    parsed_models, stored_checksums=stored_checksums
                )
                generator.generate_view_files(mf_views)
                if changed_ids or mf_views:
                    changes_detected = True
                click.echo(f"  Processed {len(file_paths)} Cube.js files ({len(changed_ids)} changed)")
        except Exception as e:
            cube_sync_error = str(e)
            click.echo(f"  Error: {cube_sync_error}", err=True)

        # Build/update state
        if previous_state and not force_full_sync:
            current_state = state_manager.merge_state(
                previous_state, manifest, manifest_nodes, file_paths, removed_models,
                output_checksums=output_checksums, changed_node_ids=changed_ids,
            )
        else:
            current_state = state_manager.create_state_from_results(
                manifest, manifest_nodes, file_paths, output_checksums=output_checksums
            )

        # Save cube sync state
        state_manager.save_state(current_state)
        click.echo(f"  State saved to {state_path}")

        if cube_sync_error:
            click.echo(f"  Error during cube generation: {cube_sync_error}", err=True)

        # ============================================================
        # STEP 1.5: Push to S3 (if configured)
        # ============================================================
        if s3_bucket and file_paths:
            click.echo("\n[S3] Pushing schemas to S3")
            click.echo("-" * 40)
            try:
                _upload_to_s3(output, s3_bucket, s3_prefix)
            except Exception as e:
                click.echo(f"  S3 upload failed: {e}", err=True)
        elif s3_bucket:
            click.echo("\n[S3] No files to push (no changes)")

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
        elif not cube_api_url:
            click.echo("  Skipped - --cube-api-url required for Superset sync")
        else:
            models_to_sync_ids = state_manager.get_models_needing_sync(current_state, 'superset')

            if not models_to_sync_ids and not force_full_sync:
                click.echo("  Skipped - all models already synced successfully")
            else:
                models_to_sync_names = set()
                for node_id in models_to_sync_ids:
                    if node_id in current_state.models:
                        model_name = Path(current_state.models[node_id].output_file).stem
                        models_to_sync_names.add(model_name)

                try:
                    connector = ConnectorRegistry.get_connector(
                        'superset',
                        url=superset_url,
                        username=superset_username,
                        password=superset_password,
                        database_name=cube_connection_name,
                    )

                    models_filter = None if force_full_sync else (models_to_sync_names or None)
                    results, dataset_map = connector.sync_from_cube_api(
                        cube_api_url=cube_api_url,
                        cube_api_secret=cube_api_secret,
                        models_filter=models_filter,
                    )

                    for r in results:
                        node_id = model_name_to_node_id.get(r.file_or_dataset)
                        if node_id:
                            state_manager.update_model_sync_status(
                                current_state, node_id, 'superset',
                                'success' if r.status == 'success' else 'failed'
                            )

                    successful = sum(1 for r in results if r.status == 'success')
                    failed = sum(1 for r in results if r.status == 'failed')
                    click.echo(f"  Synced: {successful} successful, {failed} failed")

                    # Sync RLS rules if any model has superset_rls configured
                    try:
                        access_policies = {
                            CubeGenerator._to_pascal_case(m.name): m.access_policy
                            for m in parsed_models
                            if any(
                                (p.get('row_level') or {}).get('filters')
                                for p in (m.access_policy or [])
                            )
                        }
                        if access_policies:
                            click.echo("\n  → Syncing RLS rules")
                            connector.sync_rls(access_policies, dataset_map)
                    except Exception as rls_err:
                        click.echo(f"  Warning: RLS sync failed: {rls_err}", err=True)

                except Exception as e:
                    click.echo(f"  Error: {str(e)}", err=True)
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
            click.echo(f"  Cube.js files generated: {len(file_paths)}")
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


@main.command()
@click.option('--manifest', '-m', required=True,
              help='Path to dbt manifest.json')
@click.option('--sqlalchemy-uri', '-s', required=False, default=None,
              help='DB connection URI for column type resolution')
@click.option('--catalog', '-c', required=False, default=None,
              help='Path to dbt catalog.json (alternative to sqlalchemy-uri)')
@click.option('--output', '-o', required=True,
              help='Output directory where cube YAML files are written')
# ── API mode (recommended) ────────────────────────────────────────────────────
@click.option('--cube-api-url', required=False, default=None,
              envvar='CUBEJS_API_URL',
              help='Running Cube.js API URL.  Generates YAMLs, diffs vs /meta, '
                   'queries changed cubes.  No Docker needed.')
@click.option('--cube-api-secret', required=False, default='',
              envvar='CUBEJS_API_SECRET',
              help='Cube.js API secret (Bearer token)')
@click.option('--reload-wait', default=5, type=int, show_default=True,
              help='Seconds to wait after writing YAMLs for Cube.js hot-reload (API mode)')
# ── Docker mode (fallback) ────────────────────────────────────────────────────
@click.option('--cube-image', default='cubejs/cube:latest', show_default=True,
              help='Cube.js Docker image (Docker mode only)')
@click.option('--port', default=4100, type=int, show_default=True,
              help='Local port for Cube.js container (Docker mode only)')
@click.option('--timeout', default=180, type=int, show_default=True,
              help='Seconds to wait for Cube.js startup (Docker mode only)')
@click.option('--db-type', envvar='CUBEJS_DB_TYPE', default=None)
@click.option('--db-host', envvar='CUBEJS_DB_HOST', default=None)
@click.option('--db-name', envvar='CUBEJS_DB_NAME', default=None)
@click.option('--db-user', envvar='CUBEJS_DB_USER', default=None)
@click.option('--db-pass', envvar='CUBEJS_DB_PASS', default=None)
@click.option('--db-port', envvar='CUBEJS_DB_PORT', default=None)
@click.option('--db-ssl', envvar='CUBEJS_DB_SSL', default='false')
@click.option('--api-secret', envvar='CUBEJS_API_SECRET', default='ci-test-secret',
              help='API secret for the Docker Cube.js instance (Docker mode only)')
# ── Dev schema ────────────────────────────────────────────────────────────────
@click.option('--dev-schema', required=False, default=None,
              envvar='CUBE_DEV_SCHEMA',
              help='Override DB schema in manifest (useful for CI dev target schemas)')
@click.option('--run-results', required=False, default=None,
              help='Path to dbt run_results.json. Patches schema for each succeeded '
                   'model using the actual relation_name it was built into — so Cube.js '
                   'queries the CI-built tables instead of production ones.')
@click.option('--prod-manifest', required=False, default=None,
              help='Path to the production manifest.json. When provided, generates cube '
                   'files from both manifests, diffs them by file hash, and queries only '
                   'changed/added cubes. No running Cube.js with the old schema needed. '
                   'Combine with --cube-api-url to also run query validation.')
def validate_cubes(
    manifest: str,
    sqlalchemy_uri: Optional[str],
    catalog: Optional[str],
    output: str,
    cube_api_url: Optional[str],
    cube_api_secret: str,
    reload_wait: int,
    cube_image: str,
    port: int,
    timeout: int,
    db_type: Optional[str],
    db_host: Optional[str],
    db_name: Optional[str],
    db_user: Optional[str],
    db_pass: Optional[str],
    db_port: Optional[str],
    db_ssl: str,
    api_secret: str,
    dev_schema: Optional[str],
    run_results: Optional[str],
    prod_manifest: Optional[str],
):
    """
    Validate Cube.js schemas against a running Cube.js instance (or via Docker).

    API MODE (recommended — no Docker):

      Generates YAML cube files, writes them to --output, then diffs the
      generated schema (dimensions/measures) against what the running Cube.js
      /meta API reports.  Changed and new cubes are validated with a live query.
      Checks for load errors (cubes missing from /meta after reload).

        dbt-cube-sync validate-cubes \\
          -m manifest.json -s $DB_URI \\
          --output /path/to/cube/model/cubes \\
          --cube-api-url http://cube:4000

    DOCKER MODE (fallback — spins up Cube.js via Docker):

        dbt-cube-sync validate-cubes \\
          -m manifest.json -s $DB_URI \\
          --output /tmp/cubes \\
          --db-type redshift --db-host ... --db-user ... --db-pass ...
    """
    import json as _json
    import tempfile

    try:
        click.echo("=" * 62)
        click.echo("VALIDATE CUBES")
        click.echo("=" * 62)

        # ── Load + optionally patch manifest ──────────────────────────
        with open(manifest) as f:
            manifest_data = _json.load(f)

        if dev_schema:
            patched = 0
            for node in manifest_data.get('nodes', {}).values():
                node['schema'] = dev_schema
                patched += 1
            for sm_data in manifest_data.get('semantic_models', {}).values():
                nr = sm_data.get('node_relation', {})
                if isinstance(nr, dict):
                    nr['schema_name'] = dev_schema
                    nr['schema'] = dev_schema
            click.echo(f"  Patched schema → '{dev_schema}' for all {patched} node(s)")

        if run_results:
            with open(run_results) as f:
                rr = _json.load(f)
            # relation_name format: '"db"."schema"."table"' or 'db.schema.table'
            ci_schemas: dict = {}       # uid  → ci_schema
            ci_schemas_by_name: dict = {}  # model_name → ci_schema
            for result in rr.get('results', []):
                if result.get('status') not in ('success', 'pass'):
                    continue
                uid      = result.get('unique_id', '')
                relation = result.get('relation_name') or ''
                parts    = [p.strip('"').strip('`').strip("'") for p in relation.split('.')]
                if len(parts) >= 2 and uid:
                    schema = parts[-2]  # schema is second-to-last component
                    ci_schemas[uid] = schema
                    # also key by bare model name (last segment of uid, e.g. "products")
                    ci_schemas_by_name[uid.rsplit('.', 1)[-1]] = schema
            patched = 0
            for uid, node in manifest_data.get('nodes', {}).items():
                if uid in ci_schemas:
                    node['schema'] = ci_schemas[uid]
                    patched += 1
            for uid, sm_data in manifest_data.get('semantic_models', {}).items():
                # semantic model uids are "semantic_model.*.*", not in ci_schemas;
                # match by model name instead
                sm_name = sm_data.get('name', '') or uid.rsplit('.', 1)[-1]
                schema = ci_schemas.get(uid) or ci_schemas_by_name.get(sm_name)
                if schema:
                    nr = sm_data.get('node_relation', {})
                    if isinstance(nr, dict):
                        nr['schema_name'] = schema
                        nr['schema']      = schema
                    patched += 1
            click.echo(f"  Patched schema from run_results for {patched} CI-built node(s)")

        # ── Generate cube YAML files ───────────────────────────────────
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
            _json.dump(manifest_data, tf)
            tmp_manifest_path = tf.name

        try:
            parser = DbtParser(
                manifest_path=tmp_manifest_path,
                catalog_path=catalog,
                sqlalchemy_uri=sqlalchemy_uri,
            )
            models = parser.parse_models()
            mf_models = parser.parse_metricflow_models()
            mf_views = parser.parse_metricflow_views()
            semantic_model_names = {m.name for m in mf_models}  # snake_case dbt names
            if mf_models:
                existing_names = {m.name for m in models}
                models += [m for m in mf_models if m.name not in existing_names]
        finally:
            Path(tmp_manifest_path).unlink(missing_ok=True)

        if not models:
            click.echo("  No cube models found — nothing to validate.")
            return

        # ══════════════════════════════════════════════════════════════
        # MANIFEST DIFF MODE
        # ══════════════════════════════════════════════════════════════
        if prod_manifest:
            click.echo(f"\n  Mode: Manifest Diff  (prod: {prod_manifest})")

            # ── Generate current cube files → output dir ───────────────
            output_path.mkdir(parents=True, exist_ok=True)
            generator = CubeGenerator('./cube/templates', str(output_path))
            file_paths, _, _ = generator.generate_cube_files(models)
            view_paths = generator.generate_view_files(mf_views)
            click.echo(f"  Generated {len(file_paths)} cube(s) + {len(view_paths)} view(s) → {output_path}")

            # ── Parse prod manifest and generate prod cube files → temp dir ──
            with tempfile.TemporaryDirectory() as prod_output_dir:
                prod_parser = DbtParser(
                    manifest_path=prod_manifest,
                    catalog_path=catalog,
                    sqlalchemy_uri=sqlalchemy_uri,
                )
                prod_models = prod_parser.parse_models()
                prod_mf_models = prod_parser.parse_metricflow_models()
                prod_mf_views = prod_parser.parse_metricflow_views()
                if prod_mf_models:
                    existing_names = {m.name for m in prod_models}
                    prod_models += [m for m in prod_mf_models if m.name not in existing_names]

                prod_generator = CubeGenerator('./cube/templates', prod_output_dir)
                prod_generator.generate_cube_files(prod_models)
                prod_generator.generate_view_files(prod_mf_views)
                click.echo(f"  Generated {len(prod_models)} prod cube(s) → temp dir")

                # ── Diff the two output dirs by file hash ──────────────
                prod_hashes = _load_deployed_file_hashes(deployed_dir=prod_output_dir)
                added, modified, removed = _diff_cube_files(str(output_path), prod_hashes)

            # ── Print diff report ──────────────────────────────────────
            click.echo("\n" + "─" * 62)
            click.echo("SCHEMA DIFF (prod manifest → current manifest)")
            click.echo("─" * 62)

            if added:
                click.echo(f"\n  + Added ({len(added)}):")
                for name in sorted(added):
                    click.echo(f"      {name}")
            if modified:
                click.echo(f"\n  ~ Modified ({len(modified)}):")
                for name in sorted(modified):
                    click.echo(f"      {name}")
            if removed:
                click.echo(f"\n  - Removed ({len(removed)}):")
                for name in sorted(removed):
                    click.echo(f"      {name}")
            if not added and not modified and not removed:
                click.echo("\n  No schema changes detected.")

            changed = added | modified

            # ── Query validation for changed/added cubes ───────────────
            if changed and cube_api_url:
                new_meta = _fetch_cube_api_meta(cube_api_url, cube_api_secret)

                click.echo(f"\n{'─' * 62}")
                click.echo(f"QUERY VALIDATION ({len(changed)} changed cube(s))")
                click.echo("─" * 62)

                results: list = []
                load_errors: Set[str] = set()

                for name in sorted(changed):
                    cube_info = new_meta.get(name)
                    if cube_info is None:
                        load_errors.add(name)
                        results.append((name, False, 'not found in Cube.js /meta'))
                        continue
                    ok, detail = _query_cube_via_api(name, cube_info, cube_api_url, cube_api_secret)
                    results.append((name, ok, detail))

                passed_count = sum(1 for _, ok, _ in results if ok)
                failed_count = len(results) - passed_count

                click.echo(f"\n{'─' * 62}")
                click.echo("SUMMARY")
                click.echo("─" * 62)
                for name, ok, detail in results:
                    status = "✓ PASSED" if ok else "✗ FAILED"
                    pad = max(0, 44 - len(name))
                    click.echo(f"  {status}  {name}{' ' * pad}{detail}")

                click.echo(f"\n{'─' * 62}")
                click.echo(f"  RESULT: {passed_count}/{len(results)} cubes passed")
                if load_errors:
                    click.echo(f"  LOAD ERRORS: {len(load_errors)} cube(s) failed to load")
                click.echo("=" * 62)

                if failed_count > 0 or load_errors:
                    sys.exit(1)
            elif changed:
                click.echo("\n  (no --cube-api-url provided — skipping query validation)")
                click.echo("=" * 62)
            else:
                click.echo("\n" + "=" * 62)
                click.echo("  No changed cubes — nothing to query-validate.")
                click.echo("=" * 62)

            return

        # ══════════════════════════════════════════════════════════════
        # API MODE
        # ══════════════════════════════════════════════════════════════
        if cube_api_url:
            click.echo(f"\n  Mode: API  ({cube_api_url})")

            # ── Snapshot OLD state (before writing new YAMLs) ──────────
            try:
                old_meta = _fetch_cube_api_meta(cube_api_url, cube_api_secret)
                click.echo(f"  Baseline Cube.js /meta: {len(old_meta)} cube(s)")
            except Exception as e:
                click.echo(f"  Baseline Cube.js /meta: unavailable ({e}) — treating as empty")
                old_meta = {}

            # Save old YAML state for pre-agg / access-policy diff (cubes + views)
            old_yaml_state: Dict[str, dict] = {}
            for yf in output_path.glob('*.yaml'):
                data = yaml.safe_load(yf.read_text()) or {}
                for cube in data.get('cubes', []):
                    old_yaml_state[cube['name']] = cube
                for view in data.get('views', []):
                    old_yaml_state[view['name']] = view

            # ── Generate and write new cube YAML files ─────────────────
            generator = CubeGenerator('./cube/templates', str(output_path))
            file_paths, _, _ = generator.generate_cube_files(models)
            view_paths = generator.generate_view_files(mf_views)
            click.echo(f"  Generated {len(file_paths)} cube(s) + {len(view_paths)} view(s) → {output_path}")

            # Semantic models that failed to generate (e.g. no measures)
            generated_node_ids = set(file_paths.keys())
            semantic_not_generated = [
                m for m in models
                if m.name in semantic_model_names and m.node_id not in generated_node_ids
            ]
            if semantic_not_generated:
                click.echo(f"  ⚠ Semantic models not generated: {[m.name for m in semantic_not_generated]}")

            # ── Wait for hot-reload ────────────────────────────────────
            if reload_wait > 0:
                click.echo(f"  Waiting {reload_wait}s for Cube.js to reload schemas...")
                time.sleep(reload_wait)

            # ── Snapshot NEW state ─────────────────────────────────────
            new_meta = _fetch_cube_api_meta(cube_api_url, cube_api_secret)
            click.echo(f"  New Cube.js /meta: {len(new_meta)} cube(s)")

            new_yaml_state: Dict[str, dict] = {}
            for yf in output_path.glob('*.yaml'):
                data = yaml.safe_load(yf.read_text()) or {}
                for cube in data.get('cubes', []):
                    new_yaml_state[cube['name']] = cube
                for view in data.get('views', []):
                    new_yaml_state[view['name']] = view

            # ── Load error check ──────────────────────────────────────
            # Anything generated but absent from /meta failed to load in Cube.js
            load_errors = set(new_yaml_state) - set(new_meta)

            # ── Semantic model completeness check ─────────────────────
            # Every dbt semantic model must exist in the Cube API after deploy
            semantic_cube_names = {
                generator._to_pascal_case(name) for name in semantic_model_names
            }
            missing_semantic = semantic_cube_names - set(new_meta)

            # ── API-to-API structural diff (dimensions + measures) ────
            added, modified, removed, diffs = _diff_api_states(old_meta, new_meta)

            # ── YAML diff (pre-aggregations + access policies) ────────
            yaml_diffs = _diff_yaml_states(old_yaml_state, new_yaml_state)

            # Merge YAML diffs into the report
            for name, lines in yaml_diffs.items():
                if name not in diffs:
                    diffs[name] = []
                diffs[name].extend(lines)
                if name not in added and name not in modified:
                    modified.add(name)

            changed = added | modified

            # ── Print diff report ──────────────────────────────────────
            click.echo("\n" + "─" * 62)
            click.echo("SCHEMA DIFF (old Cube API → new Cube API)")
            click.echo("─" * 62)

            if semantic_not_generated:
                click.echo(f"\n  ✗ SEMANTIC MODELS NOT GENERATED ({len(semantic_not_generated)}):")
                for m in semantic_not_generated:
                    click.echo(f"      {m.name}")

            if missing_semantic:
                click.echo(f"\n  ✗ SEMANTIC MODELS MISSING FROM CUBE API ({len(missing_semantic)}):")
                for name in sorted(missing_semantic):
                    click.echo(f"      {name}")

            if load_errors:
                click.echo(f"\n  ✗ LOAD ERRORS — generated but absent from /meta ({len(load_errors)}):")
                for name in sorted(load_errors):
                    click.echo(f"      {name}")

            if added:
                click.echo(f"\n  + Added ({len(added)}):")
                for name in sorted(added):
                    click.echo(f"      {name}")

            if modified:
                click.echo(f"\n  ~ Modified ({len(modified)}):")
                for name in sorted(modified):
                    click.echo(f"      {name}")
                    for line in diffs.get(name, []):
                        click.echo(line)

            if removed:
                click.echo(f"\n  - Removed ({len(removed)}):")
                for name in sorted(removed):
                    click.echo(f"      {name}")

            if not semantic_not_generated and not missing_semantic and not load_errors and not added and not modified and not removed:
                click.echo("\n  No schema changes detected. All semantic models present in Cube API.")

            # ── Query validation for changed/new cubes ─────────────────
            if changed:
                click.echo(f"\n{'─' * 62}")
                click.echo(f"QUERY VALIDATION ({len(changed)} changed cube(s))")
                click.echo("─" * 62)

                results: list = []
                for name in sorted(changed):
                    cube_info = new_meta.get(name, {})
                    ok, detail = _query_cube_via_api(name, cube_info, cube_api_url, cube_api_secret)
                    results.append((name, ok, detail))

                passed_count = sum(1 for _, ok, _ in results if ok)
                failed_count = len(results) - passed_count

                click.echo(f"\n{'─' * 62}")
                click.echo("SUMMARY")
                click.echo("─" * 62)
                for name, ok, detail in results:
                    status = "✓ PASSED" if ok else "✗ FAILED"
                    pad = max(0, 44 - len(name))
                    click.echo(f"  {status}  {name}{' ' * pad}{detail}")

                click.echo(f"\n{'─' * 62}")
                click.echo(f"  RESULT: {passed_count}/{len(results)} cubes passed")
                if load_errors:
                    click.echo(f"  LOAD ERRORS: {len(load_errors)} cube(s) failed to load")
                click.echo("=" * 62)

                if failed_count > 0 or load_errors or missing_semantic or semantic_not_generated:
                    sys.exit(1)
            else:
                click.echo("\n" + "=" * 62)
                if load_errors:
                    click.echo(f"  LOAD ERRORS: {len(load_errors)} cube(s) failed to load")
                if missing_semantic:
                    click.echo(f"  MISSING: {len(missing_semantic)} semantic model(s) not in Cube API")
                if semantic_not_generated:
                    click.echo(f"  NOT GENERATED: {len(semantic_not_generated)} semantic model(s) skipped")
                if load_errors or missing_semantic or semantic_not_generated:
                    sys.exit(1)
                else:
                    click.echo("  No changed cubes — nothing to query-validate.")
                click.echo("=" * 62)

            return

        # ══════════════════════════════════════════════════════════════
        # DOCKER MODE (fallback)
        # ══════════════════════════════════════════════════════════════
        from .core.cube_validator import CubeValidator, print_validation_report

        (output_path / 'model' / 'cubes').mkdir(parents=True, exist_ok=True)

        db_config: dict = {
            'CUBEJS_API_SECRET': api_secret,
            'CUBEJS_DEV_MODE': 'true',
        }
        if db_type:
            db_config['CUBEJS_DB_TYPE'] = db_type
        if db_host:
            db_config['CUBEJS_DB_HOST'] = db_host
        if db_name:
            db_config['CUBEJS_DB_NAME'] = db_name
        if db_user:
            db_config['CUBEJS_DB_USER'] = db_user
        if db_pass:
            db_config['CUBEJS_DB_PASS'] = db_pass
        if db_port:
            db_config['CUBEJS_DB_PORT'] = db_port
        if db_ssl and db_ssl.lower() not in ('false', '0', ''):
            db_config['CUBEJS_DB_SSL'] = 'true'
        if sqlalchemy_uri and not all(
            k in db_config for k in ('CUBEJS_DB_HOST', 'CUBEJS_DB_NAME')
        ):
            _parse_sqlalchemy_into_db_config(sqlalchemy_uri, db_config)

        click.echo(f"\n  Mode: Docker  ({cube_image}, port {port})")
        validator = CubeValidator(
            output_dir=str(output_path),
            db_config=db_config,
            cube_image=cube_image,
            port=port,
            startup_timeout=timeout,
        )
        try:
            validator.start()
            click.echo(f"  Waiting for Cube.js to be ready (up to {timeout}s)...")
            validator.wait_ready()
            click.echo("  Cube.js is ready.\n")
            meta = validator.get_meta()
            results = validator.validate_all(meta)
            all_passed = print_validation_report(results)
        finally:
            validator.stop()

        if not all_passed:
            sys.exit(1)

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


def _parse_sqlalchemy_into_db_config(uri: str, db_config: dict) -> None:
    """Best-effort extraction of host/name/user/pass from a SQLAlchemy URI."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        scheme = parsed.scheme.split('+')[0].lower()
        _SCHEME_MAP = {
            'redshift': 'redshift',
            'postgresql': 'postgres',
            'postgres': 'postgres',
            'snowflake': 'snowflake',
            'bigquery': 'bigquery',
            'mysql': 'mysql',
            'trino': 'trino',
            'presto': 'presto',
        }
        if scheme in _SCHEME_MAP and 'CUBEJS_DB_TYPE' not in db_config:
            db_config['CUBEJS_DB_TYPE'] = _SCHEME_MAP[scheme]
        if parsed.hostname and 'CUBEJS_DB_HOST' not in db_config:
            db_config['CUBEJS_DB_HOST'] = parsed.hostname
        if parsed.port and 'CUBEJS_DB_PORT' not in db_config:
            db_config['CUBEJS_DB_PORT'] = str(parsed.port)
        if parsed.username and 'CUBEJS_DB_USER' not in db_config:
            db_config['CUBEJS_DB_USER'] = parsed.username
        if parsed.password and 'CUBEJS_DB_PASS' not in db_config:
            from urllib.parse import unquote
            db_config['CUBEJS_DB_PASS'] = unquote(parsed.password)
        db_path = parsed.path.lstrip('/')
        if db_path and 'CUBEJS_DB_NAME' not in db_config:
            db_config['CUBEJS_DB_NAME'] = db_path
    except Exception:
        pass


@main.command()
@click.option('--manifest', '-m',
              required=True,
              help='Path to the CI-generated manifest.json (target to be updated)')
@click.option('--new-manifest', '-n',
              required=True,
              help='Path to the reference manifest.json (source of node data, e.g. from a full dbt run)')
@click.option('--run-results', '-r',
              required=True,
              help='Path to run_results.json — only nodes that succeeded here will be merged')
@click.option('--output', '-o',
              required=False,
              default=None,
              help='Output path for the aligned manifest (default: overwrite --manifest in place)')
def align_ci_manifest(
    manifest: str,
    new_manifest: str,
    run_results: str,
    output: Optional[str],
):
    """
    Align a CI manifest with a reference manifest for successfully built nodes.

    Updates nodes in the CI manifest (--manifest) with data from the reference
    manifest (--new-manifest), but only for nodes that appear in --run-results
    with a successful status ('success' or 'pass').

    Useful when the CI manifest (generated by `dbt ls`) should be enriched with
    authoritative node data from a full dbt run, scoped to only the models that
    were actually built and succeeded.

    Examples:

      # Update manifest in place
      dbt-cube-sync align-ci-manifest -m ci/manifest.json -n prod/manifest.json -r prod/run_results.json

      # Write aligned manifest to a new file
      dbt-cube-sync align-ci-manifest -m ci/manifest.json -n prod/manifest.json -r prod/run_results.json -o aligned_manifest.json
    """
    import json

    # Sections in a dbt manifest that can contain individually addressable nodes
    MANIFEST_NODE_SECTIONS = [
        'nodes', 'sources', 'macros', 'exposures', 'metrics',
        'semantic_models', 'saved_queries', 'unit_tests',
    ]

    try:
        click.echo("=" * 60)
        click.echo("ALIGN-CI-MANIFEST: Merging reference nodes into CI manifest")
        click.echo("=" * 60)

        click.echo(f"\nLoading CI manifest from {manifest}...")
        with open(manifest, 'r') as f:
            ci_manifest = json.load(f)

        click.echo(f"Loading reference manifest from {new_manifest}...")
        with open(new_manifest, 'r') as f:
            ref_manifest = json.load(f)

        click.echo(f"Loading run results from {run_results}...")
        with open(run_results, 'r') as f:
            run_results_data = json.load(f)

        # Collect unique_ids that succeeded
        succeeded_ids = {
            r['unique_id']
            for r in run_results_data.get('results', [])
            if r.get('status') in ('success', 'pass')
        }
        click.echo(f"\nFound {len(succeeded_ids)} succeeded nodes in run results")

        # Build a lookup: unique_id -> (section, node_data) across all sections of ref_manifest
        ref_lookup: dict = {}
        for section in MANIFEST_NODE_SECTIONS:
            for uid, node_data in ref_manifest.get(section, {}).items():
                ref_lookup[uid] = (section, node_data)

        # Merge succeeded nodes from ref_manifest into ci_manifest
        updated = 0
        added = 0
        not_in_ref = 0

        for uid in succeeded_ids:
            if uid not in ref_lookup:
                not_in_ref += 1
                continue

            section, node_data = ref_lookup[uid]

            # Ensure the section exists in the CI manifest
            if section not in ci_manifest:
                ci_manifest[section] = {}

            if uid in ci_manifest[section]:
                ci_manifest[section][uid] = node_data
                updated += 1
            else:
                ci_manifest[section][uid] = node_data
                added += 1

        click.echo(f"  Updated: {updated} existing nodes")
        click.echo(f"  Added:   {added} new nodes")
        if not_in_ref:
            click.echo(f"  Skipped: {not_in_ref} nodes not found in reference manifest")

        # Write output
        out_path = output or manifest
        with open(out_path, 'w') as f:
            json.dump(ci_manifest, f, indent=2)

        click.echo(f"\nAligned manifest written to {out_path}")
        click.echo("=" * 60)

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
