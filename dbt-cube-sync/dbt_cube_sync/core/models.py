"""
Pydantic models for data structures
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# MetricFlow semantic layer models
# ---------------------------------------------------------------------------

class MetricFlowDimensionTypeParams(BaseModel):
    """Type parameters for a MetricFlow time dimension"""
    time_granularity: Optional[str] = None  # day, week, month, quarter, year


class MetricFlowEntity(BaseModel):
    """Join key defined in a MetricFlow semantic model"""
    name: str
    type: str  # primary, foreign, unique, natural
    expr: Optional[str] = None
    description: Optional[str] = None
    label: Optional[str] = None


class MetricFlowDimension(BaseModel):
    """Slicing attribute defined in a MetricFlow semantic model"""
    name: str
    type: str  # categorical, time
    type_params: Optional[MetricFlowDimensionTypeParams] = None
    expr: Optional[str] = None
    description: Optional[str] = None
    label: Optional[str] = None


class MetricFlowMeasure(BaseModel):
    """Base aggregation defined in a MetricFlow semantic model"""
    name: str
    agg: str  # sum, avg, count, count_distinct, min, max
    expr: Optional[str] = None
    description: Optional[str] = None
    label: Optional[str] = None
    agg_time_dimension: Optional[str] = None


class MetricFlowSemanticModel(BaseModel):
    """MetricFlow semantic model — maps to one Cube.js cube"""
    name: str
    model: str  # ref('model_name') or plain model_name
    description: Optional[str] = None
    label: Optional[str] = None
    defaults: Optional[Dict[str, Any]] = None
    entities: List[MetricFlowEntity] = []
    dimensions: List[MetricFlowDimension] = []
    measures: List[MetricFlowMeasure] = []
    pre_aggregations: Dict[str, Any] = {}
    # Resolved from manifest
    alias: Optional[str] = None
    schema_name: Optional[str] = None
    database: Optional[str] = None


class MetricFlowTypeParams(BaseModel):
    """Type-specific parameters for a MetricFlow metric"""
    # simple
    measure: Optional[str] = None
    # derived
    expr: Optional[str] = None
    metrics: Optional[List[Dict[str, Any]]] = None
    # ratio - can be string (legacy) or object (new format)
    numerator: Optional[Any] = None  # str or dict with 'name' field
    denominator: Optional[Any] = None  # str or dict with 'name' field
    # cumulative (legacy)
    window: Optional[str] = None
    grain_to_date: Optional[str] = None
    # NEW dbt 1.12.0 format: metric aggregation parameters
    metric_aggregation_params: Optional[Dict[str, Any]] = None
    # NEW dbt 1.12.0 format: cumulative type parameters
    cumulative_type_params: Optional[Dict[str, Any]] = None


class MetricFlowMetric(BaseModel):
    """MetricFlow metric — becomes a Cube.js measure"""
    name: str
    label: Optional[str] = None
    description: Optional[str] = None
    type: str  # simple, derived, ratio, cumulative
    type_params: MetricFlowTypeParams


class DbtColumn(BaseModel):
    """Represents a dbt model column"""
    name: str
    data_type: Optional[str] = None
    description: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class DbtMetric(BaseModel):
    """Represents a dbt metric"""
    name: str
    type: str
    sql: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class DbtRefreshKey(BaseModel):
    """Represents a refresh_key configuration for pre-aggregations"""
    every: Optional[str] = None
    sql: Optional[str] = None
    incremental: Optional[bool] = None
    update_window: Optional[str] = None


class DbtPreAggregation(BaseModel):
    """Represents a dbt pre-aggregation configuration"""
    name: str
    type: str = "rollup"
    measures: Optional[List[str]] = None
    dimensions: Optional[List[str]] = None
    time_dimension: Optional[str] = None
    granularity: Optional[str] = None
    refresh_key: Optional[DbtRefreshKey] = None


class DbtModel(BaseModel):
    """Represents a parsed dbt model"""
    name: str
    alias: str
    database: str
    schema_name: str  # Renamed to avoid shadowing BaseModel.schema
    node_id: str
    columns: Dict[str, DbtColumn]
    metrics: Dict[str, DbtMetric]
    pre_aggregations: Dict[str, DbtPreAggregation] = {}


class CubeDimension(BaseModel):
    """Represents a Cube.js dimension"""
    name: str
    sql: str
    type: str
    title: Optional[str] = None
    description: Optional[str] = None


class CubeMeasure(BaseModel):
    """Represents a Cube.js measure"""
    name: str
    type: str
    sql: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class CubeRefreshKey(BaseModel):
    """Represents a Cube.js refresh_key configuration"""
    every: Optional[str] = None
    sql: Optional[str] = None
    incremental: Optional[bool] = None
    update_window: Optional[str] = None


class CubePreAggregation(BaseModel):
    """Represents a Cube.js pre-aggregation"""
    name: str
    type: str = "rollup"
    measures: Optional[List[str]] = None
    dimensions: Optional[List[str]] = None
    time_dimension: Optional[str] = None
    granularity: Optional[str] = None
    refresh_key: Optional[CubeRefreshKey] = None


class CubeSchema(BaseModel):
    """Represents a complete Cube.js schema"""
    cube_name: str
    sql: str
    dimensions: List[CubeDimension]
    measures: List[CubeMeasure]
    pre_aggregations: List[CubePreAggregation] = []


class SyncResult(BaseModel):
    """Represents the result of a sync operation"""
    file_or_dataset: str
    status: str  # 'success' or 'failed'
    message: Optional[str] = None
    error: Optional[str] = None


class ModelState(BaseModel):
    """Represents the state of a single model for incremental sync"""
    checksum: str
    has_metrics: bool
    last_generated: str
    output_file: str
    output_checksum: Optional[str] = None  # checksum of the generated .js file
    # Per-model sync status for each step
    superset_sync_status: Optional[str] = None  # 'success', 'failed', or None (not attempted)
    rag_sync_status: Optional[str] = None  # 'success', 'failed', or None (not attempted)


class SyncState(BaseModel):
    """Represents the overall state for incremental sync"""
    version: str = "1.1"
    last_sync_timestamp: str
    manifest_path: str
    models: Dict[str, ModelState] = {}