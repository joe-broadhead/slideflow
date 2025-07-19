"""JSON file data connector for Slideflow.

This module provides a connector and configuration for reading JSON files as
data sources in Slideflow presentations. It handles various JSON formats and
orientations supported by pandas, with configurable parsing options.

The JSON connector supports different JSON data structures through the 'orient'
parameter, allowing for flexible handling of various JSON formats including
records, index-oriented data, and nested structures.

Key Features:
    - Support for multiple JSON orientations (records, index, split, etc.)
    - Automatic data type inference via pandas
    - Operation logging for monitoring and debugging  
    - Path validation and error handling
    - Integration with caching system
    - Configurable parsing options

Example:
    Using the JSON connector:
    
    >>> from slideflow.data.connectors.json import JSONSourceConfig
    >>> 
    >>> # Create configuration for records-oriented JSON
    >>> config = JSONSourceConfig(
    ...     name="api_data",
    ...     type="json",
    ...     file_path="/data/api_response.json",
    ...     orient="records"
    ... )
    >>> 
    >>> # Fetch data
    >>> data = config.fetch_data()
    >>> print(f"Loaded {len(data)} rows from JSON")
"""

import pandas as pd
from pathlib import Path
from pydantic import Field, ConfigDict
from typing import Annotated, Literal, ClassVar, Type

from slideflow.constants import Defaults
from slideflow.utilities.logging import log_data_operation
from slideflow.data.connectors.base import DataConnector, BaseSourceConfig

class JSONConnector(DataConnector):
    """Data connector for reading JSON files into pandas DataFrames.
    
    This connector provides a flexible interface for loading JSON files with
    various orientations and structures. It uses pandas' read_json function
    with configurable orientation to handle different JSON formats.
    
    The connector supports all pandas JSON orientations:
    - 'records': List of dictionaries (most common for API responses)
    - 'index': Dictionary with index labels as keys
    - 'split': Dictionary with separate arrays for index, columns, and data
    - 'table': Dictionary with schema and data arrays
    - 'values': Just the values array
    
    Example:
        >>> connector = JSONConnector(
        ...     file_path="/data/users.json",
        ...     orient="records"
        ... )
        >>> data = connector.fetch_data()
        >>> print(f"Loaded {len(data)} records with {len(data.columns)} fields")
    """
    def __init__(self, file_path: str, orient: str = Defaults.JSON_ORIENT) -> None:
        """Initialize the JSON connector.
        
        Args:
            file_path: Path to the JSON file to read. Can be absolute or
                relative path as a string.
            orient: JSON orientation parameter for pandas.read_json().
                Determines how the JSON data structure is interpreted.
                Common values: 'records', 'index', 'split', 'table', 'values'.
        """
        self.file_path = file_path
        self.orient = orient

    def fetch_data(self) -> pd.DataFrame:
        """Read JSON file and return as DataFrame.
        
        Loads the JSON file using pandas with the specified orientation.
        The operation is logged with details about the file path, orientation,
        and number of rows loaded.
        
        Returns:
            DataFrame containing the JSON data with automatically inferred
            data types and structure based on the orientation parameter.
            
        Raises:
            FileNotFoundError: If the JSON file doesn't exist.
            ValueError: If the JSON format is invalid or incompatible with orientation.
            pd.errors.EmptyDataError: If the JSON file is empty.
            
        Example:
            >>> connector = JSONConnector("/data/sales.json", orient="records")
            >>> df = connector.fetch_data()
            >>> print(df.head())
        """
        df = pd.read_json(self.file_path, orient = self.orient)
        log_data_operation("fetch", "json", len(df), file_path = self.file_path, orient = self.orient)
        return df

class JSONSourceConfig(BaseSourceConfig):
    """Configuration model for JSON data sources.
    
    This configuration class defines the parameters needed to connect to
    and read JSON files with various orientations. It uses Pydantic for
    validation and type safety, ensuring that file paths are valid and
    orientation parameters are properly configured.
    
    The configuration integrates with the discriminated union system,
    using "json" as the type discriminator to automatically select this
    configuration when parsing polymorphic data source configurations.
    
    The orient parameter allows for flexible handling of different JSON
    structures, making it suitable for various data sources including
    API responses, exported data, and structured JSON files.
    
    Attributes:
        type: Always "json" for JSON data sources.
        file_path: Path to the JSON file, validated as a Path object.
        orient: JSON orientation for pandas parsing (records, index, split, etc.).
        connector_class: References JSONConnector for instantiation.
    
    Example:
        Creating a JSON data source configuration:
        
        >>> config = JSONSourceConfig(
        ...     name="user_activity",
        ...     type="json",
        ...     file_path="/data/user_events.json",
        ...     orient="records"
        ... )
        >>> 
        >>> # Use configuration to fetch data
        >>> data = config.fetch_data()
        >>> print(f"Loaded {len(data)} events from {config.file_path}")
        
        For different JSON orientations:
        
        >>> # Index-oriented JSON
        >>> config_index = JSONSourceConfig(
        ...     name="metrics",
        ...     type="json", 
        ...     file_path="/data/metrics.json",
        ...     orient="index"
        ... )
        
        From dictionary/JSON:
        
        >>> config_dict = {
        ...     "name": "api_data",
        ...     "type": "json",
        ...     "file_path": "/data/api_response.json",
        ...     "orient": "records"
        ... }
        >>> config = JSONSourceConfig(**config_dict)
    """
    type: Literal["json"] = Field("json", description = "Discriminator: this config reads from a JSON file")
    file_path: Annotated[Path, Field(..., description = "Path to the JSON file")]
    orient: Annotated[str, Field(default = Defaults.JSON_ORIENT, description = "`orient` parameter passed to pandas.read_json")]
    connector_class: ClassVar[Type[DataConnector]] = JSONConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
    )
