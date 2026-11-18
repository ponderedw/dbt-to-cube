"""
Superset connector — syncs Superset datasets from the Cube.js API.

Fetches cube definitions from Cube.js /meta, then creates, updates, and
deletes Superset datasets to match.  No local files are read or written.
"""
import json
import time
from typing import Dict, List, Optional, Tuple

import requests

from .base import BaseConnector, ConnectorRegistry
from ..core.models import SyncResult
from ..cube_auth import cube_auth_headers


class SupersetConnector(BaseConnector):
    """Apache Superset BI connector — API-to-API only."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        database_name: str = "Cube",
        **kwargs,
    ):
        super().__init__(
            url=url,
            username=username,
            password=password,
            database_name=database_name,
            **kwargs,
        )
        self.base_url = url.rstrip('/')
        self.session = requests.Session()
        self.access_token = None
        self.csrf_token = None
        self.database_id = None
        self.connect()

    def _validate_config(self) -> None:
        required = ['url', 'username', 'password']
        missing = [f for f in required if not self.config.get(f)]
        if missing:
            raise ValueError(f"Missing required config fields: {missing}")

    def connect(self) -> None:
        self._login()
        self._get_csrf_token()
        self._get_database_id()

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _login(self):
        resp = self.session.post(
            f"{self.base_url}/api/v1/security/login",
            json={
                "password": self.config['password'],
                "provider": "db",
                "refresh": "true",
                "username": self.config['username'],
            },
        )
        if resp.status_code == 401:
            raise RuntimeError(
                f"Superset auth failed (401). Check credentials. Response: {resp.text}"
            )
        resp.raise_for_status()
        self.access_token = resp.json()['access_token']
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        })

    def _get_csrf_token(self):
        resp = self.session.get(f"{self.base_url}/api/v1/security/csrf_token/")
        resp.raise_for_status()
        self.csrf_token = resp.json()['result']
        self.session.headers.update({'X-CSRFToken': self.csrf_token})

    def _get_database_id(self):
        db_name = self.config.get('database_name', 'Cube')
        resp = self.session.get(
            f"{self.base_url}/api/v1/database/",
            params={"q": json.dumps({
                "filters": [{"col": "database_name", "opr": "eq", "value": db_name}]
            })},
        )
        resp.raise_for_status()
        results = resp.json().get('result', [])
        if not results:
            raise ValueError(f"Database '{db_name}' not found in Superset. "
                             f"Create a PostgreSQL connection to Cube SQL API first.")
        self.database_id = results[0]['id']
        print(f"Found database '{db_name}' (id={self.database_id})")

    # ── API-to-API sync ───────────────────────────────────────────────────────

    def sync_from_cube_api(
        self,
        cube_api_url: str,
        cube_api_secret: str = '',
        models_filter: Optional[set] = None,
    ) -> 'Tuple[List[SyncResult], Dict[str, int]]':
        """Sync Superset datasets from the Cube.js /meta API.

        - Creates a dataset for every cube in Cube.js that doesn't exist yet.
        - Updates columns and metrics for every existing dataset.
        - Deletes Superset datasets that no longer exist in Cube.js
          (only when models_filter is None — i.e. full sync).

        Returns (results, dataset_map) where dataset_map is {cube_name: dataset_id}.
        """
        results: List[SyncResult] = []
        dataset_map: Dict[str, int] = {}

        cube_meta = self._fetch_cube_meta(cube_api_url, cube_api_secret)
        if models_filter:
            cube_meta = {k: v for k, v in cube_meta.items() if k in models_filter}
        print(f"Cube.js: {len(cube_meta)} cube(s)")

        existing = self._fetch_superset_datasets_by_name()
        print(f"Superset: {len(existing)} existing dataset(s)")

        for cube_name, cube_info in cube_meta.items():
            schema_info = self._cube_meta_to_schema_info(cube_name, cube_info)
            try:
                if cube_name in existing:
                    dataset_id = existing[cube_name]
                    self._update_dataset_metadata(dataset_id, schema_info)
                    dataset_map[cube_name] = dataset_id
                    results.append(SyncResult(file_or_dataset=cube_name, status='success', message=f'updated id={dataset_id}'))
                    print(f"  ~ {cube_name} → updated (id={dataset_id})")
                else:
                    dataset_id = self._create_new_dataset(schema_info)
                    dataset_map[cube_name] = dataset_id
                    results.append(SyncResult(file_or_dataset=cube_name, status='success', message=f'created id={dataset_id}'))
                    print(f"  + {cube_name} → created (id={dataset_id})")
            except Exception as e:
                results.append(SyncResult(file_or_dataset=cube_name, status='failed', error=str(e)))
                print(f"  ✗ {cube_name}: {e}")

        # Remove orphans only on full sync
        if not models_filter:
            for name in sorted(set(existing) - set(cube_meta)):
                try:
                    self.session.delete(
                        f"{self.base_url}/api/v1/dataset/{existing[name]}"
                    ).raise_for_status()
                    results.append(SyncResult(file_or_dataset=name, status='success', message=f'deleted orphan id={existing[name]}'))
                    print(f"  - {name} → deleted (no longer in Cube)")
                except Exception as e:
                    results.append(SyncResult(file_or_dataset=name, status='failed', error=str(e)))
                    print(f"  ✗ {name} (delete): {e}")

        ok = sum(1 for r in results if r.status == 'success')
        fail = sum(1 for r in results if r.status == 'failed')
        print(f"\nDone: {ok} succeeded, {fail} failed")
        return results, dataset_map

    # Not used in API mode — raises to prevent accidental invocation
    def sync_cube_schemas(self, cube_dir: str, models_filter=None) -> List[SyncResult]:
        raise NotImplementedError(
            "SupersetConnector only supports API-to-API sync. "
            "Use sync_from_cube_api() or pass --cube-api-url."
        )

    def sync_single_schema(self, cube_file_path: str) -> SyncResult:
        raise NotImplementedError(
            "SupersetConnector only supports API-to-API sync. "
            "Use sync_from_cube_api() or pass --cube-api-url."
        )

    # ── Cube /meta helpers ────────────────────────────────────────────────────

    def _fetch_cube_meta(self, cube_api_url: str, cube_api_secret: str) -> Dict[str, dict]:
        url = cube_api_url.rstrip('/') + '/cubejs-api/v1/meta'
        headers = cube_auth_headers(cube_api_secret)
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return {c['name']: c for c in resp.json().get('cubes', [])}

    def _cube_meta_to_schema_info(self, cube_name: str, cube_info: dict) -> dict:
        dimensions = []
        for dim in cube_info.get('dimensions', []):
            field = dim['name'].split('.')[-1]
            if field.startswith('__'):
                continue
            dim_type = dim.get('type', 'string')
            dimensions.append({
                'column_name': field,
                'type': self._cube_type_to_sql(dim_type),
                'verbose_name': dim.get('shortTitle') or dim.get('title') or field,
                'description': dim.get('description') or '',
                'is_dttm': dim_type == 'time',
                'groupby': True,
                'filterable': True,
            })

        measures = []
        for m in cube_info.get('measures', []):
            field = m['name'].split('.')[-1]
            m_type = m.get('type', 'sum')
            description = m.get('description') or ''
            measures.append({
                'metric_name': m.get('shortTitle') or m.get('title') or field,
                'expression': f'MEASURE({cube_name}.{field})',
                'verbose_name': m.get('shortTitle') or m.get('title') or field,
                'description': f'{description} ({m_type})' if description else '',
                'metric_type': 'simple',
            })

        return {
            'cube_name': cube_name,
            'schema': 'public',
            'table_name': cube_name,
            'dimensions': dimensions,
            'measures': measures,
        }

    # ── Superset dataset CRUD ─────────────────────────────────────────────────

    def _fetch_superset_datasets_by_name(self) -> Dict[str, int]:
        resp = self.session.get(
            f"{self.base_url}/api/v1/dataset/",
            params={"q": json.dumps({
                "filters": [
                    {"col": "database", "opr": "rel_o_m", "value": self.database_id}
                ],
                "page_size": 1000,
            })},
        )
        resp.raise_for_status()
        return {r['table_name']: r['id'] for r in resp.json().get('result', [])}

    def _create_new_dataset(self, schema_info: dict) -> int:
        resp = self.session.post(
            f"{self.base_url}/api/v1/dataset/",
            json={
                "database": self.database_id,
                "schema": schema_info['schema'],
                "table_name": schema_info['table_name'],
                "normalize_columns": False,
                "always_filter_main_dttm": False,
            },
        )
        if resp.status_code != 201:
            raise RuntimeError(f"Failed to create dataset: {resp.status_code} {resp.text}")
        dataset_id = resp.json()['id']
        self._update_dataset_metadata(dataset_id, schema_info)
        return dataset_id

    def _update_dataset_metadata(self, dataset_id: int, schema_info: dict):
        dataset_url = f"{self.base_url}/api/v1/dataset/{dataset_id}"

        self.session.put(f"{dataset_url}/refresh")
        time.sleep(1)

        resp = self.session.get(dataset_url)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch dataset {dataset_id}: {resp.status_code}")

        ds = resp.json()['result']
        measure_fields = {
            m['expression'].split('.')[-1].rstrip(')')
            for m in schema_info['measures']
        }
        updated_columns = self._merge_columns(
            ds.get('columns', []), schema_info['dimensions'], measure_fields
        )
        updated_metrics = self._merge_metrics(ds.get('metrics', []), schema_info['measures'])

        put_resp = self.session.put(
            dataset_url,
            json={'columns': updated_columns, 'metrics': updated_metrics},
        )
        if put_resp.status_code != 200:
            raise RuntimeError(
                f"Failed to update dataset {dataset_id}: {put_resp.status_code} {put_resp.text}"
            )

    def _merge_columns(self, existing: list, dimensions: list,
                       measure_fields: set = None) -> list:
        _SKIP = {'created_on', 'changed_on', 'type_generic', 'uuid', 'advanced_data_type'}
        dim_lookup = {d['column_name'].lower(): d for d in dimensions}
        hidden = measure_fields or set()
        result = []
        for col in existing:
            clean = {k: v for k, v in col.items() if k not in _SKIP}
            col_name = col['column_name'].lower()
            if col_name.startswith('__') or col_name in hidden:
                clean.update({'is_active': False, 'groupby': False, 'filterable': False})
            else:
                dim = dim_lookup.get(col_name)
                if dim:
                    clean.update({
                        'verbose_name': dim['verbose_name'],
                        'description': dim['description'],
                        'is_dttm': dim['is_dttm'],
                        'groupby': dim['groupby'],
                        'filterable': dim['filterable'],
                        'is_active': True,
                    })
            result.append(clean)
        return result

    def _merge_metrics(self, existing: list, measures: list) -> list:
        _SKIP = {'created_on', 'changed_on', 'uuid'}
        # Keep manually-created metrics (non-MEASURE() expressions).
        manual = [
            {k: v for k, v in m.items() if k not in _SKIP}
            for m in existing
            if not (m.get('expression') or '').strip().upper().startswith('MEASURE(')
        ]
        # Build lookup of existing MEASURE() metrics by name so we can reuse their id.
        existing_by_name = {
            m.get('metric_name', ''): m
            for m in existing
            if (m.get('expression') or '').strip().upper().startswith('MEASURE(')
        }
        new_metrics = []
        for measure in measures:
            new_m = {
                'metric_name': measure['metric_name'],
                'verbose_name': measure['verbose_name'],
                'expression': measure['expression'],
                'description': measure['description'],
                'metric_type': 'simple',
                'currency': None,
                'd3format': None,
                'extra': None,
                'warning_text': None,
            }
            # Reuse existing id so Superset updates rather than creates.
            prev = existing_by_name.get(measure['metric_name'])
            if prev and 'id' in prev:
                new_m['id'] = prev['id']
            new_metrics.append(new_m)
        return manual + new_metrics

    @staticmethod
    def _cube_type_to_sql(cube_type: str) -> str:
        return {
            'string': 'VARCHAR',
            'number': 'NUMERIC',
            'time': 'TIMESTAMP',
            'boolean': 'BOOLEAN',
        }.get(cube_type, 'VARCHAR')


    def sync_rls(
        self,
        access_policies: Dict[str, List[dict]],
        dataset_map: Dict[str, int],
    ) -> List[SyncResult]:
        """Create or update Superset RLS rules derived from Cube.js row_level.filters.

        ``{ userAttributes.xxx }`` values are translated to Superset Jinja vars
        ``{{ xxx }}``.  One RLS rule is created per access_policy entry that has
        a ``row_level.filters`` list.  Rules are keyed on
        ``(dataset_id, group)`` for idempotent re-runs.

        Example dbt meta:

          cube_access_policy:
            - group: dbt_public
              row_level:
                filters:
                  - member: country
                    operator: equals
                    values:
                      - "{ userAttributes.country }"

        → Superset clause:  country = '{{ country }}'
        """
        results: List[SyncResult] = []
        existing = self._fetch_rls_rules_by_key()

        for cube_name, policies in access_policies.items():
            dataset_id = dataset_map.get(cube_name)
            if not dataset_id:
                continue

            for policy in policies:
                filters = (policy.get('row_level') or {}).get('filters', [])
                if not filters:
                    continue

                group = policy.get('group', 'rls')
                clauses = [self._filter_to_sql(f) for f in filters if self._filter_to_sql(f)]
                if not clauses:
                    continue

                clause = ' AND '.join(clauses)
                rule_name = f"{cube_name} {group}"
                rule_key = f"{dataset_id}:{group}"
                payload: dict = {
                    'clause': clause,
                    'filter_type': 'Regular',
                    'group_key': group,
                    'name': rule_name,
                    'roles': [],
                    'tables': [{'id': dataset_id}],
                }

                try:
                    if rule_key in existing:
                        rule_id = existing[rule_key]
                        resp = self.session.put(
                            f"{self.base_url}/api/v1/rowlevelsecurity/{rule_id}",
                            json=payload,
                        )
                        if resp.status_code not in (200, 201):
                            raise RuntimeError(f"{resp.status_code} {resp.text}")
                        results.append(SyncResult(file_or_dataset=rule_name, status='success',
                                                  message=f'rls updated id={rule_id}'))
                        print(f"  ~ RLS {rule_name!r} → updated (id={rule_id})")
                    else:
                        resp = self.session.post(
                            f"{self.base_url}/api/v1/rowlevelsecurity/",
                            json=payload,
                        )
                        if resp.status_code not in (200, 201):
                            raise RuntimeError(f"{resp.status_code} {resp.text}")
                        rule_id = resp.json().get('id')
                        results.append(SyncResult(file_or_dataset=rule_name, status='success',
                                                  message=f'rls created id={rule_id}'))
                        print(f"  + RLS {rule_name!r} → created (id={rule_id})")
                except Exception as e:
                    results.append(SyncResult(file_or_dataset=rule_name, status='failed', error=str(e)))
                    print(f"  ✗ RLS {rule_name!r}: {e}")

        ok = sum(1 for r in results if r.status == 'success')
        fail = sum(1 for r in results if r.status == 'failed')
        if results:
            print(f"\nRLS sync: {ok} succeeded, {fail} failed")
        return results

    @staticmethod
    def _filter_to_sql(f: dict) -> str:
        """Translate a Cube.js row_level filter to a Superset SQL WHERE clause.

        ``{ userAttributes.xxx }`` → Jinja ``{{ xxx }}``
        """
        import re

        member = f.get('member', '')
        operator = f.get('operator', 'equals')
        values = f.get('values', [])
        if not member or not values:
            return ''

        def _jinja(v: str) -> str:
            m = re.match(r'\{\s*userAttributes\.(\w+)\s*\}', str(v))
            return f'{{{{ {m.group(1)} }}}}' if m else str(v)

        jinja_values = [_jinja(v) for v in values]

        if operator in ('equals', 'contains'):
            if len(jinja_values) == 1:
                return f"{member} = '{jinja_values[0]}'"
            return f"{member} IN ({', '.join(repr(v) for v in jinja_values)})"
        if operator in ('notEquals', 'notContains'):
            if len(jinja_values) == 1:
                return f"{member} != '{jinja_values[0]}'"
            return f"{member} NOT IN ({', '.join(repr(v) for v in jinja_values)})"
        if operator == 'startsWith':
            return f"{member} LIKE '{jinja_values[0]}%'"
        if operator == 'endsWith':
            return f"{member} LIKE '%{jinja_values[0]}'"
        return ''

    def _fetch_rls_rules_by_key(self) -> Dict[str, int]:
        """Return existing RLS rules keyed by '{dataset_id}:{group_key}' → rule_id."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v1/rowlevelsecurity/",
                params={'q': '{"page_size": 1000}'},
            )
            if resp.status_code != 200:
                return {}
            result: Dict[str, int] = {}
            for rule in resp.json().get('result', []):
                gk = rule.get('group_key', '')
                for tbl in rule.get('tables', []):
                    key = f"{tbl.get('id')}:{gk}"
                    result[key] = rule['id']
            return result
        except Exception:
            return {}


ConnectorRegistry.register('superset', SupersetConnector)
