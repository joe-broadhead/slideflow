"""Union type for all data source configurations in Slideflow.

This module defines the discriminated union type that encompasses all available
data source configurations. It provides type safety for polymorphic data source
handling throughout the Slideflow system.

The DataSourceConfig union uses Pydantic's discriminator feature to automatically
select the correct configuration type based on the 'type' field, enabling
type-safe serialization and deserialization of configuration data.

Key Features:
    - Type discrimination based on 'type' field
    - Automatic validation and type selection
    - Support for all available data source types
    - Integration with JSON/YAML configuration files
    - Type safety for polymorphic configurations

Example:
    Using the union type in configuration:
    
    >>> from slideflow.data.connectors import DataSourceConfig
    >>> 
    >>> # CSV configuration
    >>> csv_config = {
    ...     "type": "csv",
    ...     "name": "sales_data",
    ...     "file_path": "/data/sales.csv"
    ... }
    >>> 
    >>> # JSON configuration  
    >>> json_config = {
    ...     "type": "json",
    ...     "name": "api_data",
    ...     "file_path": "/data/api_response.json"
    ... }
    >>> 
    >>> # Both are valid DataSourceConfig instances
    >>> configs = [csv_config, json_config]
    >>> for config in configs:
    ...     data = config.fetch_data()

Supported Data Source Types:
    - "csv": CSV file data sources
    - "json": JSON file data sources
    - "databricks": Databricks SQL warehouse connections
    - "dbt": DBT models in Databricks
"""

from pydantic import Field
from typing import Annotated, Union

from slideflow.data.connectors.csv import CSVSourceConfig
from slideflow.data.connectors.json import JSONSourceConfig
from slideflow.data.connectors.dbt import DBTDatabricksSourceConfig
from slideflow.data.connectors.databricks import DatabricksSourceConfig

DataSourceConfig = Annotated[
    Union[
        CSVSourceConfig,
        JSONSourceConfig,
        DatabricksSourceConfig,
        DBTDatabricksSourceConfig
    ],
    Field(discriminator = "type"),
]
"""Discriminated union of all available data source configurations.

This type represents any valid data source configuration that can be used
throughout the Slideflow system. The discriminator field 'type' is used to
automatically select the correct configuration class during validation.

The union includes all currently supported data source types:
- CSVSourceConfig: For CSV file data sources
- JSONSourceConfig: For JSON file data sources  
- DatabricksSourceConfig: For Databricks SQL warehouse connections
- DBTDatabricksSourceConfig: For DBT models in Databricks

Example:
    >>> config_data = {
    ...     "type": "csv",
    ...     "name": "sales",
    ...     "file_path": "/data/sales.csv"
    ... }
    >>> config = DataSourceConfig(**config_data)
    >>> isinstance(config, CSVSourceConfig)  # True
"""