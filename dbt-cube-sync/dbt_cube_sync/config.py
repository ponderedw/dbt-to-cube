"""
Configuration management for dbt-cube-sync
"""
import yaml
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, validator


class ConnectorConfig(BaseModel):
    """Configuration for a BI tool connector"""
    type: str
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database_name: Optional[str] = "Cube"
    
    @validator('type')
    def validate_type(cls, v):
        supported_types = ['superset', 'tableau', 'powerbi']
        if v not in supported_types:
            raise ValueError(f"Unsupported connector type: {v}. Supported: {supported_types}")
        return v


class Config(BaseModel):
    """Main configuration class"""
    connectors: Dict[str, ConnectorConfig] = {}
    
    @classmethod
    def load_from_file(cls, config_path: str) -> 'Config':
        """
        Load configuration from YAML file
        
        Args:
            config_path: Path to the YAML configuration file
            
        Returns:
            Config instance
        """
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)
        
        # Parse connector configurations
        connectors = {}
        for name, connector_data in data.get('connectors', {}).items():
            connectors[name] = ConnectorConfig(**connector_data)
        
        return cls(connectors=connectors)
    
    def get_connector_config(self, connector_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific connector
        
        Args:
            connector_name: Name of the connector (e.g., 'superset')
            
        Returns:
            Dictionary with connector configuration
        """
        if connector_name not in self.connectors:
            available = list(self.connectors.keys())
            raise ValueError(f"Connector '{connector_name}' not found in config. Available: {available}")
        
        config = self.connectors[connector_name]
        return config.dict()
    
    def save_to_file(self, config_path: str) -> None:
        """
        Save configuration to YAML file
        
        Args:
            config_path: Path to save the configuration file
        """
        data = {
            'connectors': {
                name: config.dict() for name, config in self.connectors.items()
            }
        }
        
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2)
    
    @classmethod
    def create_sample_config(cls, config_path: str) -> None:
        """
        Create a sample configuration file
        
        Args:
            config_path: Path to create the sample configuration file
        """
        sample_config = cls(
            connectors={
                'superset': ConnectorConfig(
                    type='superset',
                    url='http://localhost:8088',
                    username='admin',
                    password='admin',
                    database_name='Cube'
                ),
                'tableau': ConnectorConfig(
                    type='tableau',
                    url='https://your-tableau-server.com',
                    username='your-username',
                    password='your-password'
                ),
                'powerbi': ConnectorConfig(
                    type='powerbi',
                    # Add PowerBI specific configuration fields here
                )
            }
        )
        
        sample_config.save_to_file(config_path)