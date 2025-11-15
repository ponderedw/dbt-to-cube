"""
Pydantic models for data structures
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel


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


class DbtModel(BaseModel):
    """Represents a parsed dbt model"""
    name: str
    database: str
    schema_name: str  # Renamed to avoid shadowing BaseModel.schema
    node_id: str
    columns: Dict[str, DbtColumn]
    metrics: Dict[str, DbtMetric]


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


class CubeSchema(BaseModel):
    """Represents a complete Cube.js schema"""
    cube_name: str
    sql: str
    dimensions: List[CubeDimension]
    measures: List[CubeMeasure]


class SyncResult(BaseModel):
    """Represents the result of a sync operation"""
    file_or_dataset: str
    status: str  # 'success' or 'failed'
    message: Optional[str] = None
    error: Optional[str] = None