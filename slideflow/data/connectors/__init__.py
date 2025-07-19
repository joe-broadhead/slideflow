"""Data connectors for various data sources in Slideflow.

This module provides a unified interface for connecting to and retrieving data
from different data sources. The connector system follows a plugin architecture
where each data source type has its own specialized connector implementation.

The connector system includes:
    - Base classes and interfaces for all connectors
    - Configuration models for each data source type
    - Specialized connectors for CSV, JSON, Databricks, and DBT
    - Connection management and data retrieval abstractions

Architecture:
    All connectors inherit from DataConnector base class and implement a
    consistent interface for data retrieval. Each connector type has an
    associated configuration class that defines the parameters needed
    to connect to that specific data source.

Key Features:
    - Consistent interface across all data source types
    - Type-safe configuration with Pydantic models
    - Connection pooling and caching support
    - Error handling and retry mechanisms
    - Extensible design for adding new data sources

Example:
    Using connectors to fetch data:
    
    >>> from slideflow.data.connectors import CSVConnector, CSVSourceConfig
    >>> 
    >>> # Create configuration
    >>> config = CSVSourceConfig(file_path="/data/sales.csv")
    >>> 
    >>> # Create connector and fetch data
    >>> connector = CSVConnector(config)
    >>> data = connector.fetch_data()
    >>> print(f"Loaded {len(data)} rows")

Available Connectors:
    - CSVConnector: For CSV file data sources
    - JSONConnector: For JSON file data sources  
    - DatabricksConnector: For Databricks SQL warehouse connections
    - DBTDatabricksConnector: For DBT models in Databricks

Available Configurations:
    - CSVSourceConfig: Configuration for CSV files
    - JSONSourceConfig: Configuration for JSON files
    - DatabricksSourceConfig: Configuration for Databricks connections
    - DBTDatabricksSourceConfig: Configuration for DBT models
"""

from slideflow.data.connectors.connect import DataSourceConfig
from slideflow.data.connectors.csv import CSVConnector, CSVSourceConfig
from slideflow.data.connectors.base import DataConnector, BaseSourceConfig
from slideflow.data.connectors.json import JSONConnector, JSONSourceConfig
from slideflow.data.connectors.dbt import DBTDatabricksConnector, DBTDatabricksSourceConfig
from slideflow.data.connectors.databricks import DatabricksConnector, DatabricksSourceConfig

__all__ = [
    'DataConnector',
    'BaseSourceConfig',
    'CSVConnector',
    'CSVSourceConfig',
    'JSONConnector',
    'JSONSourceConfig',
    'DatabricksConnector',
    'DatabricksSourceConfig',
    'DBTDatabricksConnector',
    'DBTDatabricksSourceConfig',
    'DataSourceConfig'
]
