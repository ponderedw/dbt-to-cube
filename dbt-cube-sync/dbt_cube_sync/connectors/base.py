"""
Abstract base connector for BI tools
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pathlib import Path

from ..core.models import SyncResult


class BaseConnector(ABC):
    """Abstract base class for BI tool connectors"""
    
    def __init__(self, **config):
        """
        Initialize the connector with configuration
        
        Args:
            **config: Connector-specific configuration parameters
        """
        self.config = config
        self._validate_config()
    
    @abstractmethod
    def _validate_config(self) -> None:
        """Validate the provided configuration"""
        pass
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the BI tool"""
        pass
    
    @abstractmethod
    def sync_cube_schemas(self, cube_dir: str) -> List[SyncResult]:
        """
        Sync all Cube.js schemas from directory to BI tool
        
        Args:
            cube_dir: Directory containing Cube.js schema files
            
        Returns:
            List of SyncResult objects with status of each file
        """
        pass
    
    @abstractmethod
    def sync_single_schema(self, cube_file_path: str) -> SyncResult:
        """
        Sync a single Cube.js schema file to BI tool
        
        Args:
            cube_file_path: Path to the Cube.js schema file
            
        Returns:
            SyncResult object with status
        """
        pass
    
    def _get_cube_files(self, cube_dir: str) -> List[Path]:
        """Get all .js files from the cube directory"""
        cube_path = Path(cube_dir)
        if not cube_path.exists():
            raise FileNotFoundError(f"Cube directory not found: {cube_dir}")
        
        return list(cube_path.glob("*.js"))
    
    def get_connector_type(self) -> str:
        """Return the type of this connector"""
        return self.__class__.__name__.replace('Connector', '').lower()


class ConnectorRegistry:
    """Registry for managing available connectors"""
    
    _connectors: Dict[str, type] = {}
    
    @classmethod
    def register(cls, name: str, connector_class: type) -> None:
        """Register a connector class"""
        cls._connectors[name] = connector_class
    
    @classmethod
    def get_connector(cls, name: str, **config) -> BaseConnector:
        """Get an instance of a registered connector"""
        if name not in cls._connectors:
            available = list(cls._connectors.keys())
            raise ValueError(f"Unknown connector '{name}'. Available: {available}")
        
        return cls._connectors[name](**config)
    
    @classmethod
    def list_connectors(cls) -> List[str]:
        """List all registered connector names"""
        return list(cls._connectors.keys())