"""
MetricFlow semantic layer parser.

Reads MetricFlow semantic_models + metrics from the compiled manifest.json
(manifest['semantic_models'] / manifest['metrics']).  dbt compiles all YAML
definitions into the manifest, so no separate file scan is required.

Each MetricFlowSemanticModel becomes one DbtModel (→ one Cube.js file).
MetricFlow entities and dimensions → Cube.js dimensions.
MetricFlow measures + metrics → Cube.js measures.
"""
import re
from typing import Dict, List, Optional, Tuple

from .models import (
    DbtModel,
    DbtColumn,
    DbtMetric,
    DbtPreAggregation,
    DbtRefreshKey,
    MetricFlowSemanticModel,
    MetricFlowEntity,
    MetricFlowDimension,
    MetricFlowDimensionTypeParams,
    MetricFlowMeasure,
    MetricFlowMetric,
    MetricFlowTypeParams,
)

# MetricFlow agg → Cube.js measure type
_AGG_MAP: Dict[str, str] = {
    'sum': 'sum',
    'avg': 'avg',
    'average': 'avg',
    'count': 'count',
    'count_distinct': 'countDistinct',
    'count_distinct_approx': 'countDistinctApprox',
    'min': 'min',
    'max': 'max',
}

# MetricFlow dimension type → SQL data type for Cube.js
_DIM_TYPE_MAP: Dict[str, str] = {
    'time': 'timestamp',
    'categorical': 'varchar',
}


def _extract_ref_name(model_ref: str) -> str:
    """Extract model name from ``ref('model_name')`` or return the string as-is."""
    if not model_ref:
        return ''
    m = re.match(r"ref\(['\"](.+?)['\"]\)", model_ref.strip())
    return m.group(1) if m else model_ref.strip()


def _parse_measure_name(value: object) -> Optional[str]:
    """Accept ``measure`` field as plain string or ``{name: ...}`` dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get('name')
    return str(value)


class MetricFlowParser:
    """
    Parses MetricFlow definitions and converts them to ``DbtModel`` objects
    that feed into the standard ``CubeGenerator`` pipeline.
    """

    def __init__(self, manifest: dict):
        """
        Args:
            manifest: Parsed dbt manifest.json.  MetricFlow definitions are read
                      from ``manifest['semantic_models']`` and ``manifest['metrics']``,
                      exactly as dbt compiles them.
        """
        self.manifest = manifest
        self._node_lookup: Dict[str, dict] = self._build_node_lookup()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> List[DbtModel]:
        """Return a list of DbtModel objects built from MetricFlow definitions."""
        semantic_models, metrics = self._load()
        if not semantic_models:
            return []
        return self._to_dbt_models(semantic_models, metrics)

    # ------------------------------------------------------------------
    # Loading: manifest vs. YAML files
    # ------------------------------------------------------------------

    def _load(
        self,
    ) -> Tuple[List[MetricFlowSemanticModel], List[MetricFlowMetric]]:
        return self._from_manifest()

    # -- manifest ----------------------------------------------------------

    def _from_manifest(
        self,
    ) -> Tuple[List[MetricFlowSemanticModel], List[MetricFlowMetric]]:
        sms = []
        for sm_data in self.manifest.get('semantic_models', {}).values():
            sm = self._parse_sm_manifest(sm_data)
            if sm:
                sms.append(sm)

        metrics = []
        for m_data in self.manifest.get('metrics', {}).values():
            metric = self._parse_metric_dict(m_data)
            if metric:
                metrics.append(metric)

        return sms, metrics

    def _parse_sm_manifest(self, data: dict) -> Optional[MetricFlowSemanticModel]:
        try:
            node_rel = data.get('node_relation') or {}
            config_meta = (data.get('config') or {}).get('meta') or {}
            pre_aggs_raw = config_meta.get('pre_aggregations') or {}
            return MetricFlowSemanticModel(
                name=data['name'],
                model=data.get('model', ''),
                description=data.get('description'),
                label=data.get('label'),
                defaults=data.get('defaults'),
                entities=self._parse_entities(data.get('entities', [])),
                dimensions=self._parse_dimensions(data.get('dimensions', [])),
                measures=self._parse_measures(data.get('measures', [])),
                pre_aggregations=pre_aggs_raw,
                alias=node_rel.get('alias'),
                schema_name=node_rel.get('schema_name') or node_rel.get('schema'),
                database=node_rel.get('database'),
            )
        except Exception as exc:
            print(f"  Warning: skipping semantic model '{data.get('name', '?')}': {exc}")
            return None

    # -- pre-aggregation parser --------------------------------------------

    @staticmethod
    def _parse_pre_aggregations(raw: dict) -> Dict[str, DbtPreAggregation]:
        result: Dict[str, DbtPreAggregation] = {}
        for name, cfg in (raw or {}).items():
            if not isinstance(cfg, dict):
                continue
            rk_raw = cfg.get('refresh_key')
            refresh_key = None
            if isinstance(rk_raw, dict):
                refresh_key = DbtRefreshKey(
                    every=rk_raw.get('every'),
                    sql=rk_raw.get('sql'),
                    incremental=rk_raw.get('incremental'),
                    update_window=rk_raw.get('update_window'),
                )
            result[name] = DbtPreAggregation(
                name=name,
                type=cfg.get('type', 'rollup'),
                measures=cfg.get('measures', []),
                dimensions=cfg.get('dimensions', []),
                time_dimension=cfg.get('time_dimension'),
                granularity=cfg.get('granularity'),
                refresh_key=refresh_key,
            )
        return result

    # -- shared field parsers ----------------------------------------------

    @staticmethod
    def _parse_entities(raw: list) -> List[MetricFlowEntity]:
        out = []
        for e in raw or []:
            if not isinstance(e, dict):
                continue
            out.append(MetricFlowEntity(
                name=e['name'],
                type=e.get('type', 'natural'),
                expr=e.get('expr'),
                description=e.get('description'),
                label=e.get('label'),
            ))
        return out

    @staticmethod
    def _parse_dimensions(raw: list) -> List[MetricFlowDimension]:
        out = []
        for d in raw or []:
            if not isinstance(d, dict):
                continue
            tp_raw = d.get('type_params')
            tp = MetricFlowDimensionTypeParams(**tp_raw) if isinstance(tp_raw, dict) else None
            out.append(MetricFlowDimension(
                name=d['name'],
                type=d.get('type', 'categorical'),
                type_params=tp,
                expr=d.get('expr'),
                description=d.get('description'),
                label=d.get('label'),
            ))
        return out

    @staticmethod
    def _parse_measures(raw: list) -> List[MetricFlowMeasure]:
        out = []
        for m in raw or []:
            if not isinstance(m, dict):
                continue
            out.append(MetricFlowMeasure(
                name=m['name'],
                agg=m.get('agg', 'sum'),
                expr=m.get('expr'),
                description=m.get('description'),
                label=m.get('label'),
                agg_time_dimension=m.get('agg_time_dimension'),
            ))
        return out

    def _parse_metric_dict(self, data: dict) -> Optional[MetricFlowMetric]:
        try:
            tp_raw = data.get('type_params') or {}
            numerator = tp_raw.get('numerator')
            denominator = tp_raw.get('denominator')
            tp = MetricFlowTypeParams(
                measure=_parse_measure_name(tp_raw.get('measure')),
                expr=tp_raw.get('expr'),
                metrics=[
                    {'name': _parse_measure_name(m) or ''}
                    for m in (tp_raw.get('metrics') or [])
                    if _parse_measure_name(m)
                ],
                numerator=_parse_measure_name(numerator) if isinstance(numerator, dict) else numerator,
                denominator=_parse_measure_name(denominator) if isinstance(denominator, dict) else denominator,
                window=tp_raw.get('window'),
                grain_to_date=tp_raw.get('grain_to_date'),
                # NEW dbt 1.12.0 format: include metric_aggregation_params
                metric_aggregation_params=tp_raw.get('metric_aggregation_params'),
            )
            return MetricFlowMetric(
                name=data['name'],
                label=data.get('label'),
                description=data.get('description'),
                type=data.get('type', 'simple'),
                type_params=tp,
            )
        except Exception as exc:
            print(f"  Warning: skipping metric '{data.get('name', '?')}': {exc}")
            return None

    # ------------------------------------------------------------------
    # Conversion: MetricFlow → DbtModel
    # ------------------------------------------------------------------

    def _to_dbt_models(
        self,
        semantic_models: List[MetricFlowSemanticModel],
        metrics: List[MetricFlowMetric],
    ) -> List[DbtModel]:
        # measure_name → semantic model (to resolve simple metric targets)
        measure_to_sm: Dict[str, MetricFlowSemanticModel] = {}
        for sm in semantic_models:
            for measure in sm.measures:
                measure_to_sm[measure.name] = sm

        # metric_name → MetricFlowMetric
        metric_by_name: Dict[str, MetricFlowMetric] = {m.name: m for m in metrics}

        # Assign each metric to the semantic model that owns its base measure(s)
        metric_to_sm_name: Dict[str, str] = {}
        for metric in metrics:
            sm_name = self._resolve_sm_for_metric(metric, measure_to_sm, metric_by_name)
            if sm_name:
                metric_to_sm_name[metric.name] = sm_name

        # Group metrics by target semantic model
        sm_metrics: Dict[str, List[MetricFlowMetric]] = {sm.name: [] for sm in semantic_models}
        for metric in metrics:
            target = metric_to_sm_name.get(metric.name)
            if target and target in sm_metrics:
                sm_metrics[target].append(metric)

        # Convert each semantic model
        dbt_models: List[DbtModel] = []
        for sm in semantic_models:
            dbt_model = self._sm_to_dbt_model(sm, sm_metrics.get(sm.name, []))
            if dbt_model:
                dbt_models.append(dbt_model)

        return dbt_models

    def _resolve_sm_for_metric(
        self,
        metric: MetricFlowMetric,
        measure_to_sm: Dict[str, MetricFlowSemanticModel],
        metric_by_name: Dict[str, MetricFlowMetric],
        _depth: int = 0,
    ) -> Optional[str]:
        """Recursively find which semantic model owns the base measure(s) for a metric."""
        if _depth > 5:
            return None

        if metric.type == 'simple':
            # NEW dbt 1.12.0 format: Check metric_aggregation_params.semantic_model
            if (hasattr(metric.type_params, 'metric_aggregation_params') and
                metric.type_params.metric_aggregation_params and
                metric.type_params.metric_aggregation_params.get('semantic_model')):
                return metric.type_params.metric_aggregation_params['semantic_model']

            # LEGACY format: Check measure reference
            base = metric.type_params.measure
            if base and base in measure_to_sm:
                return measure_to_sm[base].name

        elif metric.type in ('derived', 'ratio'):
            refs: List[str] = []
            if metric.type == 'derived' and metric.type_params.metrics:
                refs = [m.get('name', '') for m in metric.type_params.metrics if m.get('name')]
            elif metric.type == 'ratio':
                if metric.type_params.numerator:
                    refs.append(metric.type_params.numerator)
                if metric.type_params.denominator:
                    refs.append(metric.type_params.denominator)

            for ref_name in refs:
                # Direct measure reference
                if ref_name in measure_to_sm:
                    return measure_to_sm[ref_name].name
                # Metric reference (recurse)
                ref_metric = metric_by_name.get(ref_name)
                if ref_metric:
                    result = self._resolve_sm_for_metric(
                        ref_metric, measure_to_sm, metric_by_name, _depth + 1
                    )
                    if result:
                        return result

        elif metric.type == 'cumulative':
            base = metric.type_params.measure
            if base and base in measure_to_sm:
                return measure_to_sm[base].name

        return None

    def _sm_to_dbt_model(
        self,
        sm: MetricFlowSemanticModel,
        assigned_metrics: List[MetricFlowMetric],
    ) -> Optional[DbtModel]:
        """Convert one MetricFlowSemanticModel (+ its assigned metrics) to a DbtModel."""

        # Resolve table coordinates from manifest when not already set
        alias = sm.alias
        schema_name = sm.schema_name
        database = sm.database

        if not alias or not schema_name:
            model_name = _extract_ref_name(sm.model)
            node = self._node_lookup.get(model_name, {})
            alias = alias or node.get('alias', model_name)
            schema_name = schema_name or node.get('schema', '')
            database = database or node.get('database', '')

        # Build columns: entities + dimensions
        columns: Dict[str, DbtColumn] = {}

        for entity in sm.entities:
            columns[entity.name] = DbtColumn(
                name=entity.name,
                data_type='varchar',
                description=entity.description or f"{entity.type} key",
                meta={'label': entity.label or entity.name.replace('_', ' ').title()},
            )

        for dim in sm.dimensions:
            data_type = _DIM_TYPE_MAP.get(dim.type, 'varchar')
            columns[dim.name] = DbtColumn(
                name=dim.name,
                data_type=data_type,
                description=dim.description,
                meta={'label': dim.label or dim.name.replace('_', ' ').title()},
            )

        # Build measures: base measures first, then MetricFlow metrics
        metrics: Dict[str, DbtMetric] = {}

        for measure in sm.measures:
            cube_type = _AGG_MAP.get(measure.agg.lower(), 'sum')
            metrics[measure.name] = DbtMetric(
                name=measure.name,
                type=cube_type,
                sql=measure.expr or measure.name,
                title=measure.label or measure.name.replace('_', ' ').title(),
                description=measure.description,
            )

        for metric in assigned_metrics:
            dbt_metric = self._convert_metric(metric, sm.measures)
            if dbt_metric and dbt_metric.name not in metrics:
                metrics[dbt_metric.name] = dbt_metric

        if not metrics:
            return None

        return DbtModel(
            name=sm.name,
            alias=alias,
            database=database or '',
            schema_name=schema_name or '',
            node_id=f"semantic_model.{sm.name}.{sm.name}",
            columns=columns,
            metrics=metrics,
            pre_aggregations=self._parse_pre_aggregations(sm.pre_aggregations),
        )

    def _convert_metric(
        self,
        metric: MetricFlowMetric,
        sm_measures: List[MetricFlowMeasure],
    ) -> Optional[DbtMetric]:
        """Convert a MetricFlowMetric to a DbtMetric for inclusion in a cube."""
        measure_by_name = {m.name: m for m in sm_measures}

        if metric.type == 'simple':
            # NEW dbt 1.12.0 format: Get aggregation info from metric_aggregation_params
            if (metric.type_params.metric_aggregation_params and
                metric.type_params.metric_aggregation_params.get('agg') and
                metric.type_params.metric_aggregation_params.get('expr')):

                agg_params = metric.type_params.metric_aggregation_params
                cube_type = _AGG_MAP.get(agg_params['agg'].lower(), 'sum')
                sql_expr = agg_params['expr']

                return DbtMetric(
                    name=metric.name,
                    type=cube_type,
                    sql=sql_expr,
                    title=metric.label or metric.name.replace('_', ' ').title(),
                    description=metric.description,
                )

            # LEGACY format: Look for measure reference
            base_name = metric.type_params.measure
            base = measure_by_name.get(base_name) if base_name else None
            if base:
                cube_type = _AGG_MAP.get(base.agg.lower(), 'sum')
                sql_expr = base.expr or base.name
            else:
                cube_type = 'sum'
                sql_expr = base_name or metric.name
            return DbtMetric(
                name=metric.name,
                type=cube_type,
                sql=sql_expr,
                title=metric.label or metric.name.replace('_', ' ').title(),
                description=metric.description,
            )

        elif metric.type == 'derived':
            expr = metric.type_params.expr or ''
            # Wrap referenced metric names with ${...} for Cube.js
            for ref in (metric.type_params.metrics or []):
                ref_name = ref.get('name', '')
                if ref_name:
                    expr = re.sub(
                        rf'\b{re.escape(ref_name)}\b',
                        f'${{{ref_name}}}',
                        expr,
                    )
            return DbtMetric(
                name=metric.name,
                type='number',
                sql=expr,
                title=metric.label or metric.name.replace('_', ' ').title(),
                description=metric.description,
            )

        elif metric.type == 'ratio':
            num = metric.type_params.numerator
            den = metric.type_params.denominator
            if not num or not den:
                return None
            return DbtMetric(
                name=metric.name,
                type='number',
                sql=f'${{{num}}} / NULLIF(${{{den}}}, 0)',
                title=metric.label or metric.name.replace('_', ' ').title(),
                description=metric.description,
            )

        elif metric.type == 'cumulative':
            # runningTotal in Cube.js generates multi-subquery SQL for every query
            # on the cube, even when unrelated measures are selected. Use `sum`
            # instead — the running-total view is a BI/visualization-layer concern.
            base_name = metric.type_params.measure
            base = measure_by_name.get(base_name) if base_name else None
            cube_type = _AGG_MAP.get(base.agg.lower(), 'sum') if base else 'sum'
            sql_expr = (base.expr or base.name) if base else (base_name or metric.name)
            return DbtMetric(
                name=metric.name,
                type=cube_type,
                sql=sql_expr,
                title=metric.label or metric.name.replace('_', ' ').title(),
                description=metric.description,
            )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_node_lookup(self) -> Dict[str, dict]:
        lookup: Dict[str, dict] = {}
        for node_data in self.manifest.get('nodes', {}).values():
            if node_data.get('resource_type') == 'model':
                lookup[node_data['name']] = node_data
        return lookup
