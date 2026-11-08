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
    CubeJoin,
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


def _convert_mf_filter_to_cube(filter_str: str) -> str:
    """Convert a MetricFlow where-filter expression to a Cube.js SQL fragment.

    MetricFlow syntax         → Cube.js SQL
    {{ Dimension('x') }}      → ${CUBE}.x
    {{ TimeDimension('x', …) }}  → ${CUBE}.x
    {{ Metric('x') }}         → ${x}
    """
    if not filter_str:
        return filter_str
    result = re.sub(r"\{\{\s*Dimension\(['\"](\w+)['\"]\)\s*\}\}", r"${CUBE}.\1", filter_str)
    result = re.sub(r"\{\{\s*TimeDimension\(['\"](\w+)['\"].*?\)\s*\}\}", r"${CUBE}.\1", result)
    result = re.sub(r"\{\{\s*Metric\(['\"](\w+)['\"]\)\s*\}\}", r"${\1}", result)
    return result.strip()


def _map_dbt_format(format_str: Optional[str]) -> Optional[str]:
    """Map a dbt/MetricFlow format hint to a Cube.js format string.

    Cube.js built-in values: 'percent', 'currency', 'number'.
    Other strings are passed through for custom renderers.
    """
    if not format_str:
        return None
    fmt = format_str.strip()
    fmt_lower = fmt.lower()
    if fmt_lower == 'percent' or '%' in fmt:
        return 'percent'
    if fmt_lower == 'currency' or fmt.startswith('$'):
        return 'currency'
    # Pass other strings through (e.g. "0.00" for downstream BI)
    return fmt or None


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
        # First pass: parse all semantic models and metrics
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

        # Second pass: For new format, create virtual measures from simple metrics
        # when semantic models have empty measures arrays
        self._enrich_semantic_models_with_virtual_measures(sms, metrics)

        return sms, metrics

    def _enrich_semantic_models_with_virtual_measures(
        self,
        semantic_models: List[MetricFlowSemanticModel],
        metrics: List[MetricFlowMetric]
    ):
        """
        For the new dbt 1.12+ format, create virtual measures from simple metrics
        that have metric_aggregation_params pointing to semantic models with empty measures.
        """
        # Group metrics by semantic model they reference
        metrics_by_sm: Dict[str, List[MetricFlowMetric]] = {}
        for metric in metrics:
            if (metric.type == 'simple' and
                metric.type_params.metric_aggregation_params and
                metric.type_params.metric_aggregation_params.get('semantic_model')):

                sm_name = metric.type_params.metric_aggregation_params['semantic_model']
                if sm_name not in metrics_by_sm:
                    metrics_by_sm[sm_name] = []
                metrics_by_sm[sm_name].append(metric)

        # For each semantic model with empty measures, create virtual measures from its metrics
        for sm in semantic_models:
            if not sm.measures and sm.name in metrics_by_sm:
                virtual_measures = []
                for metric in metrics_by_sm[sm.name]:
                    agg_params = metric.type_params.metric_aggregation_params
                    # In new format, expr is at type_params.expr level, not inside metric_aggregation_params
                    expr = metric.type_params.expr
                    virtual_measure = MetricFlowMeasure(
                        name=metric.name,  # Use metric name as measure name for virtual measures
                        agg=agg_params.get('agg', 'sum'),
                        expr=expr,  # This is the actual SQL expression like 'order_amount', '1', 'customer_id'
                        description=metric.description,
                        label=metric.label,
                        agg_time_dimension=agg_params.get('agg_time_dimension'),
                    )
                    virtual_measures.append(virtual_measure)

                # Replace empty measures with virtual ones
                sm.measures = virtual_measures

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
            meta = m.get('meta') or {}
            # filter can live at top level OR in meta (to bypass dbt's Jinja2 rendering)
            filter_val = m.get('filter') or meta.get('filter')
            out.append(MetricFlowMeasure(
                name=m['name'],
                agg=m.get('agg', 'sum'),
                expr=m.get('expr'),
                description=m.get('description'),
                label=m.get('label'),
                agg_time_dimension=m.get('agg_time_dimension'),
                filter=filter_val,
                format=m.get('format') or meta.get('format'),
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
                numerator=numerator,  # Keep as-is for new object format or legacy string
                denominator=denominator,  # Keep as-is for new object format or legacy string
                window=tp_raw.get('window'),
                grain_to_date=tp_raw.get('grain_to_date'),
                # NEW dbt 1.12.0 format: include metric_aggregation_params
                metric_aggregation_params=tp_raw.get('metric_aggregation_params'),
                # NEW dbt 1.12.0 format: include cumulative_type_params
                cumulative_type_params=tp_raw.get('cumulative_type_params'),
            )
            # dbt 1.12 moved meta from top-level to config.meta on metrics.
            # Support both locations for backward compatibility.
            meta = data.get('meta') or {}
            config_meta = (data.get('config') or {}).get('meta') or {}
            # filter can live at top level (manifest-compiled value) or in meta.
            # Native MetricFlow format stores filter as:
            #   {'where_filters': [{'where_sql_template': "{{ Dimension('entity__col') }} = 'val'"}]}
            # Convert to Cube.js ${CUBE}.col syntax.
            raw_filter = data.get('filter') or meta.get('filter') or config_meta.get('filter')
            if isinstance(raw_filter, dict):
                where_filters = raw_filter.get('where_filters') or []
                sql_parts = []
                for wf in where_filters:
                    tmpl = wf.get('where_sql_template', '')
                    if tmpl:
                        tmpl = re.sub(
                            r"\{\{\s*Dimension\('(?:[^']+__)?([^']+)'\)\s*\}\}",
                            r"${CUBE}.\1",
                            tmpl,
                        )
                        sql_parts.append(tmpl.strip())
                filter_val = ' AND '.join(sql_parts) if sql_parts else None
            else:
                filter_val = raw_filter
            return MetricFlowMetric(
                name=data['name'],
                label=data.get('label'),
                description=data.get('description'),
                type=data.get('type', 'simple'),
                type_params=tp,
                filter=filter_val,
                format=data.get('format') or meta.get('format') or config_meta.get('format'),
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

        # Build cross-SM join indexes from entity relationships.
        # Cardinality is derived from the entity types on each side:
        #   my foreign  → their primary  : many_to_one
        #   my primary  → their primary  : one_to_one
        #   my foreign  → their foreign  : many_to_many
        primary_entity_index: Dict[str, List[tuple]] = {}
        foreign_entity_index: Dict[str, List[tuple]] = {}
        for sm in semantic_models:
            for entity in sm.entities:
                if entity.type in ('primary', 'unique'):
                    if entity.name not in primary_entity_index:
                        primary_entity_index[entity.name] = []
                    primary_entity_index[entity.name].append(
                        (sm.name, entity.expr or entity.name)
                    )
                elif entity.type == 'foreign':
                    if entity.name not in foreign_entity_index:
                        foreign_entity_index[entity.name] = []
                    foreign_entity_index[entity.name].append(
                        (sm.name, entity.expr or entity.name)
                    )

        # Convert each semantic model and attach joins
        dbt_models: List[DbtModel] = []
        for sm in semantic_models:
            dbt_model = self._sm_to_dbt_model(
                sm,
                sm_metrics.get(sm.name, []),
                primary_entity_index,
                foreign_entity_index,
                metric_to_sm_name=metric_to_sm_name,
            )
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
            if (metric.type_params.metric_aggregation_params and
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
                # NEW format: numerator/denominator are objects with 'name' field
                if isinstance(metric.type_params.numerator, dict):
                    num_name = metric.type_params.numerator.get('name')
                    if num_name:
                        refs.append(num_name)
                elif metric.type_params.numerator:  # LEGACY format: plain string
                    refs.append(metric.type_params.numerator)

                if isinstance(metric.type_params.denominator, dict):
                    den_name = metric.type_params.denominator.get('name')
                    if den_name:
                        refs.append(den_name)
                elif metric.type_params.denominator:  # LEGACY format: plain string
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
            # NEW dbt 1.12.0 format: Check cumulative_type_params.metric.name
            if (metric.type_params.cumulative_type_params and
                metric.type_params.cumulative_type_params.get('metric') and
                metric.type_params.cumulative_type_params['metric'].get('name')):

                input_metric_name = metric.type_params.cumulative_type_params['metric']['name']
                # Recursively resolve the input metric's semantic model
                ref_metric = metric_by_name.get(input_metric_name)
                if ref_metric:
                    result = self._resolve_sm_for_metric(
                        ref_metric, measure_to_sm, metric_by_name, _depth + 1
                    )
                    if result:
                        return result

            # LEGACY format: Check measure reference
            base = metric.type_params.measure
            if base and base in measure_to_sm:
                return measure_to_sm[base].name

        return None

    @staticmethod
    def _to_pascal_case(text: str) -> str:
        words = re.sub(r'[^a-zA-Z0-9]', ' ', text).split()
        return ''.join(w.capitalize() for w in words if w)

    def _sm_to_dbt_model(
        self,
        sm: MetricFlowSemanticModel,
        assigned_metrics: List[MetricFlowMetric],
        primary_entity_index: Optional[Dict[str, List[tuple]]] = None,
        foreign_entity_index: Optional[Dict[str, List[tuple]]] = None,
        metric_to_sm_name: Optional[Dict[str, str]] = None,
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
            # entity.name is the logical join name (e.g. "product");
            # entity.expr is the physical column (e.g. "product_id").
            # The dict key / Cube.js dimension name stays as entity.name;
            # sql overrides the SQL expression so the generated query uses the real column.
            is_pk = entity.type in ('primary', 'unique')
            columns[entity.name] = DbtColumn(
                name=entity.name,
                data_type='varchar',
                description=entity.description or f"{entity.type} key",
                meta={
                    'label': entity.label or entity.name.replace('_', ' ').title(),
                    'primary-key': is_pk,
                },
                sql=entity.expr if entity.expr and entity.expr != entity.name else None,
            )

        for dim in sm.dimensions:
            data_type = _DIM_TYPE_MAP.get(dim.type, 'varchar')
            columns[dim.name] = DbtColumn(
                name=dim.name,
                data_type=data_type,
                description=dim.description,
                meta={'label': dim.label or dim.name.replace('_', ' ').title()},
                sql=dim.expr if dim.expr and dim.expr != dim.name else None,
            )

        # Build measures: base measures first, then MetricFlow metrics
        metrics: Dict[str, DbtMetric] = {}

        for measure in sm.measures:
            cube_type = _AGG_MAP.get(measure.agg.lower(), 'sum')
            m_filters = None
            if measure.filter:
                m_filters = [_convert_mf_filter_to_cube(measure.filter)]
            metrics[measure.name] = DbtMetric(
                name=measure.name,
                type=cube_type,
                sql=measure.expr or measure.name,
                title=measure.label or measure.name.replace('_', ' ').title(),
                description=measure.description,
                format=_map_dbt_format(measure.format),
                filters=m_filters,
            )

        for metric in assigned_metrics:
            dbt_metric = self._convert_metric(
                metric, sm.measures,
                metric_to_sm_name=metric_to_sm_name,
                current_sm_name=sm.name,
            )
            if dbt_metric:
                # Always override: for dbt v2, the metric carries label/format/filter
                # that virtual measures lack. For legacy format, metric names differ
                # from measure names so overriding is safe.
                metrics[dbt_metric.name] = dbt_metric

        if not metrics:
            return None

        # Build Cube.js joins from entity relationships.
        # Cardinality is derived from entity types on each side:
        #   my foreign → their primary  : many_to_one  (Cube.js belongs_to)
        #   my primary → their primary  : one_to_one   (Cube.js has_one)
        #   my foreign → their foreign  : many_to_many — NOT supported by Cube.js; skipped
        #
        # For one_to_one both SMs see each other in the index and would each create
        # a join, forming a circular reference. Break the tie: only the SM whose name
        # is alphabetically first defines the join.
        joins: List[CubeJoin] = []
        my_cube_name = self._to_pascal_case(sm.name)
        seen_joins: set = set()

        def _add_joins(my_entity, targets, relationship: str) -> None:
            my_col = my_entity.expr or my_entity.name
            for target_sm_name, target_expr in targets:
                if target_sm_name == sm.name:
                    continue
                # Avoid circular A→B / B→A for one_to_one: only the alphabetically
                # first SM defines the join.
                if relationship == 'one_to_one' and sm.name > target_sm_name:
                    continue
                target_cube = self._to_pascal_case(target_sm_name)
                key = (target_cube, my_col, target_expr)
                if key in seen_joins:
                    continue
                seen_joins.add(key)
                join_sql = (
                    f"${{{my_cube_name}}}.{my_col} = "
                    f"${{{target_cube}}}.{target_expr}"
                )
                joins.append(CubeJoin(
                    name=target_cube,
                    sql=join_sql,
                    relationship=relationship,
                ))

        for entity in sm.entities:
            if entity.type == 'foreign':
                if primary_entity_index:
                    _add_joins(entity, primary_entity_index.get(entity.name, []), 'many_to_one')
                # many_to_many (foreign → foreign) is not supported in Cube.js; skipped
            elif entity.type in ('primary', 'unique'):
                if primary_entity_index:
                    _add_joins(entity, primary_entity_index.get(entity.name, []), 'one_to_one')

        return DbtModel(
            name=sm.name,
            alias=alias,
            database=database or '',
            schema_name=schema_name or '',
            node_id=f"semantic_model.{sm.name}.{sm.name}",
            columns=columns,
            metrics=metrics,
            pre_aggregations=self._parse_pre_aggregations(sm.pre_aggregations),
            joins=joins,
        )

    def _convert_metric(
        self,
        metric: MetricFlowMetric,
        sm_measures: List[MetricFlowMeasure],
        metric_to_sm_name: Optional[Dict[str, str]] = None,
        current_sm_name: Optional[str] = None,
    ) -> Optional[DbtMetric]:
        """Convert a MetricFlowMetric to a DbtMetric for inclusion in a cube."""
        measure_by_name = {m.name: m for m in sm_measures}

        # Build common fields
        # dbt v2 auto-populates label = metric.name when no explicit label is set.
        # Treat that as "no label" so we fall through to the auto-title-case.
        explicit_label = metric.label if metric.label and metric.label != metric.name else None
        title = explicit_label or metric.name.replace('_', ' ').title()
        fmt = _map_dbt_format(metric.format)
        cube_filters = [_convert_mf_filter_to_cube(metric.filter)] if metric.filter else None

        if metric.type == 'simple':
            # NEW dbt 1.12.0 format: Get aggregation info from metric_aggregation_params
            if (metric.type_params.metric_aggregation_params and
                metric.type_params.metric_aggregation_params.get('agg') and
                metric.type_params.expr):

                agg_params = metric.type_params.metric_aggregation_params
                cube_type = _AGG_MAP.get(agg_params['agg'].lower(), 'sum')
                sql_expr = metric.type_params.expr

                return DbtMetric(
                    name=metric.name,
                    type=cube_type,
                    sql=sql_expr,
                    title=title,
                    description=metric.description,
                    format=fmt,
                    filters=cube_filters,
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
                title=title,
                description=metric.description,
                format=fmt,
                filters=cube_filters,
            )

        elif metric.type == 'derived':
            expr = metric.type_params.expr or ''
            for ref in (metric.type_params.metrics or []):
                ref_name = ref.get('name', '')
                if not ref_name:
                    continue
                # Qualify cross-SM references as ${CubeName.measure_name}
                ref_sm = (metric_to_sm_name or {}).get(ref_name)
                if ref_sm and current_sm_name and ref_sm != current_sm_name:
                    cube_ref = f'${{{self._to_pascal_case(ref_sm)}.{ref_name}}}'
                else:
                    cube_ref = f'${{{ref_name}}}'
                expr = re.sub(
                    rf'\b{re.escape(ref_name)}\b',
                    cube_ref,
                    expr,
                )
            return DbtMetric(
                name=metric.name,
                type='number',
                sql=expr,
                title=title,
                description=metric.description,
                format=fmt,
                filters=cube_filters,
            )

        elif metric.type == 'ratio':
            num_name = None
            den_name = None

            if isinstance(metric.type_params.numerator, dict):
                num_name = metric.type_params.numerator.get('name')
            else:
                num_name = metric.type_params.numerator

            if isinstance(metric.type_params.denominator, dict):
                den_name = metric.type_params.denominator.get('name')
            else:
                den_name = metric.type_params.denominator

            if not num_name or not den_name:
                return None

            return DbtMetric(
                name=metric.name,
                type='number',
                sql=f'${{{num_name}}} / NULLIF(${{{den_name}}}, 0)',
                title=title,
                description=metric.description,
                format=fmt,
                filters=cube_filters,
            )

        elif metric.type == 'cumulative':
            # runningTotal in Cube.js generates multi-subquery SQL for every query
            # on the cube, even when unrelated measures are selected. Use `sum`
            # instead — the running-total view is a BI/visualization-layer concern.

            input_metric_name = None
            if (metric.type_params.cumulative_type_params and
                metric.type_params.cumulative_type_params.get('metric') and
                metric.type_params.cumulative_type_params['metric'].get('name')):
                input_metric_name = metric.type_params.cumulative_type_params['metric']['name']

            base_name = metric.type_params.measure
            base = measure_by_name.get(base_name) if base_name else None
            if not base and input_metric_name:
                base = measure_by_name.get(input_metric_name)
            cube_type = _AGG_MAP.get(base.agg.lower(), 'sum') if base else 'sum'
            sql_expr = (base.expr or base.name) if base else (input_metric_name or base_name or metric.name)

            return DbtMetric(
                name=metric.name,
                type=cube_type,
                sql=sql_expr,
                title=title,
                description=metric.description,
                format=fmt,
                filters=cube_filters,
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
