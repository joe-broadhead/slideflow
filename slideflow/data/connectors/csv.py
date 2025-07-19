"""CSV file data connector for Slideflow.

This module provides a connector and configuration for reading CSV files as
data sources in Slideflow presentations. It handles file path validation,
data loading with pandas, and integration with the logging system.

The CSV connector is one of the most commonly used connectors for static
data sources, providing a simple way to load tabular data from CSV files
into presentations.

Key Features:
    - Simple file path-based configuration
    - Automatic data type inference via pandas
    - Operation logging for monitoring and debugging
    - Path validation and error handling
    - Integration with caching system

Example:
    Using the CSV connector:
    
    >>> from slideflow.data.connectors.csv import CSVSourceConfig
    >>> 
    >>> # Create configuration
    >>> config = CSVSourceConfig(
    ...     name="sales_data",
    ...     type="csv",
    ...     file_path="/data/sales.csv"
    ... )
    >>> 
    >>> # Fetch data
    >>> data = config.fetch_data()
    >>> print(f"Loaded {len(data)} rows from CSV")
"""

import pandas as pd
from pathlib import Path
from pydantic import Field, ConfigDict
from typing import Annotated, Literal, ClassVar, Type

from slideflow.utilities.logging import log_data_operation
from slideflow.data.connectors.base import DataConnector, BaseSourceConfig

class CSVConnector(DataConnector):
    """Data connector for reading CSV files.
    
    This connector provides a simple interface for loading CSV files into
    pandas DataFrames. It uses pandas' read_csv function with default
    parameters, which handles most common CSV formats automatically.
    
    The connector logs data operations for monitoring and debugging purposes,
    recording the operation type, source type, and number of rows loaded.
    
    Example:
        >>> connector = CSVConnector(file_path="/data/sales.csv")
        >>> data = connector.fetch_data()
        >>> print(f"Loaded {len(data)} rows with {len(data.columns)} columns")
    """
    def __init__(self, file_path: str) -> None:
        """Initialize the CSV connector.
        
        Args:
            file_path: Path to the CSV file to read. Can be absolute or
                relative path as a string.
        """
        self.file_path = file_path

    def fetch_data(self) -> pd.DataFrame:
        """Read CSV file and return as DataFrame.
        
        Loads the CSV file using pandas with default parameters. The operation
        is logged with details about the file path and number of rows loaded.
        
        Returns:
            DataFrame containing the CSV data with automatically inferred
            data types and column names from the first row.
            
        Raises:
            FileNotFoundError: If the CSV file doesn't exist.
            pd.errors.EmptyDataError: If the CSV file is empty.
            pd.errors.ParserError: If the CSV file has parsing errors.
            
        Example:
            >>> connector = CSVConnector("/data/sales.csv")
            >>> df = connector.fetch_data()
            >>> print(df.head())
        """
        df = pd.read_csv(self.file_path)
        log_data_operation("fetch", "csv", len(df), file_path=self.file_path)
        return df

class CSVSourceConfig(BaseSourceConfig):
    """Configuration model for CSV data sources.
    
    This configuration class defines the parameters needed to connect to
    and read CSV files. It uses Pydantic for validation and type safety,
    ensuring that file paths are valid and properly formatted.
    
    The configuration integrates with the discriminated union system,
    using "csv" as the type discriminator to automatically select this
    configuration when parsing polymorphic data source configurations.
    
    Attributes:
        type: Always "csv" for CSV data sources.
        file_path: Path to the CSV file, validated as a Path object.
        connector_class: References CSVConnector for instantiation.
    
    Example:
        Creating a CSV data source configuration:
        
        >>> config = CSVSourceConfig(
        ...     name="quarterly_sales",
        ...     type="csv",
        ...     file_path="/data/q3_sales.csv"
        ... )
        >>> 
        >>> # Use configuration to fetch data
        >>> data = config.fetch_data()
        >>> print(f"Loaded {len(data)} rows from {config.file_path}")
        
        From dictionary/JSON:
        
        >>> config_dict = {
        ...     "name": "sales_data",
        ...     "type": "csv",
        ...     "file_path": "/data/sales.csv"
        ... }
        >>> config = CSVSourceConfig(**config_dict)
    """
    type: Literal["csv"] = Field("csv", description = "Discriminator: this config reads from a CSV file")
    file_path: Annotated[Path, Field(..., description = "Path to the CSV file")]
    connector_class: ClassVar[Type[DataConnector]] = CSVConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
    )
