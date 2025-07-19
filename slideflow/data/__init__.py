
"""Data management and connectivity system for Slideflow.

This module provides the complete data infrastructure for Slideflow presentations,
including data source connectivity, caching, and transformation capabilities.
It offers a unified interface for accessing various data sources while maintaining
performance through intelligent caching and connection management.

The data system is built around several key components:
    - Data connectors for various source types (CSV, JSON, Databricks, DBT)
    - Thread-safe caching system for performance optimization
    - Configuration models for type-safe data source definitions
    - Connection management with automatic resource cleanup

Architecture:
    The data system follows a plugin architecture where each data source type
    has its own specialized connector implementation. All connectors share a
    common interface defined by the DataConnector base class, ensuring
    consistent behavior across different data sources.

Key Features:
    - Multiple data source support (files, databases, APIs, transformations)
    - Automatic caching with intelligent cache key generation
    - Type-safe configuration with Pydantic models
    - Connection pooling and resource management
    - Comprehensive logging and performance monitoring
    - Extensible design for adding new data sources

Performance Optimizations:
    - Global caching system prevents redundant data fetching
    - Connection reuse for database sources
    - Thread-safe operations for concurrent access
    - Memory-efficient reference storage in cache

Example:
    Basic data source usage:
    
    >>> from slideflow.data import CSVSourceConfig, get_data_cache
    >>> 
    >>> # Configure a CSV data source
    >>> config = CSVSourceConfig(
    ...     name="sales_data",
    ...     type="csv",
    ...     file_path="/data/sales.csv"
    ... )
    >>> 
    >>> # Fetch data (automatically cached)
    >>> data = config.fetch_data()
    >>> print(f"Loaded {len(data)} rows")
    
    Working with multiple data sources:
    
    >>> from slideflow.data import DataSourceConfig
    >>> 
    >>> # Polymorphic configuration
    >>> sources = [
    ...     {"type": "csv", "name": "sales", "file_path": "/data/sales.csv"},
    ...     {"type": "databricks", "name": "users", "query": "SELECT * FROM users"}
    ... ]
    >>> 
    >>> for source_config in sources:
    ...     config = DataSourceConfig(**source_config)
    ...     data = config.fetch_data()
    ...     print(f"{config.name}: {len(data)} rows")
    
    Cache management:
    
    >>> cache = get_data_cache()
    >>> print(f"Cache contains {cache.size} datasets")
    >>> cache.clear()  # Clear cache when needed

Available Data Sources:
    - CSV files: Simple file-based tabular data
    - JSON files: Structured data with various orientations
    - Databricks: SQL queries against Databricks warehouses
    - DBT models: Compiled transformations with Databricks execution

Components:
    DataSourceCache: Thread-safe singleton cache for DataFrame storage
    DataConnector: Abstract base class for all data connectors
    BaseSourceConfig: Base configuration model for data sources
    DataSourceConfig: Discriminated union of all available configurations
"""

from slideflow.data.cache import DataSourceCache, get_data_cache
from slideflow.data.connectors.connect import DataSourceConfig
from slideflow.data.connectors import (
    DataConnector,
    BaseSourceConfig,
    CSVConnector,
    CSVSourceConfig,
    JSONConnector,
    JSONSourceConfig,
    DatabricksConnector,
    DatabricksSourceConfig,
    DBTDatabricksConnector,
    DBTDatabricksSourceConfig
)

__all__ = [
    'DataSourceCache',
    'get_data_cache',
    'DataSourceConfig',
    # Plus all connector exports from connectors/__init__.py
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
]