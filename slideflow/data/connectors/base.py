"""Base classes and interfaces for data connectors in Slideflow.

This module provides the foundational abstractions for the data connector system,
including the base DataConnector class and BaseSourceConfig model. These classes
establish the contract that all concrete connector implementations must follow.

The base system provides:
    - Abstract interface for data retrieval
    - Connection management with context manager support
    - Configuration validation and instantiation
    - Integration with the global caching system
    - Type-safe configuration with Pydantic models

Example:
    Creating a custom connector:
    
    >>> class MyConnector(DataConnector):
    ...     def __init__(self, api_key: str):
    ...         self.api_key = api_key
    ...     
    ...     def fetch_data(self) -> pd.DataFrame:
    ...         # Implementation for fetching data
    ...         return pd.DataFrame({"col1": [1, 2, 3]})
    
    >>> class MySourceConfig(BaseSourceConfig):
    ...     type: str = "my_source"
    ...     api_key: str
    ...     connector_class = MyConnector
"""

import pandas as pd
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated, ClassVar, Type, Any, Optional

from slideflow.data.cache import get_data_cache

class DataConnector(ABC):
    """Abstract base class for all data connectors in Slideflow.
    
    This class defines the interface that all data connectors must implement
    to integrate with the Slideflow data system. It provides connection management
    capabilities and context manager support for resource cleanup.
    
    The connector system follows a consistent pattern where each connector:
    1. Implements fetch_data() to retrieve data as a pandas DataFrame
    2. Optionally implements connect()/disconnect() for connection management
    3. Supports context manager usage for automatic resource cleanup
    
    Connection Management:
        Connectors can optionally implement connection management by overriding
        the connect() and disconnect() methods. This is useful for data sources
        that require persistent connections or have connection pooling.
    
    Example:
        Creating a simple connector:
        
        >>> class APIConnector(DataConnector):
        ...     def __init__(self, api_url: str, api_key: str):
        ...         self.api_url = api_url
        ...         self.api_key = api_key
        ...         self.client = None
        ...     
        ...     def connect(self):
        ...         self.client = APIClient(self.api_url, self.api_key)
        ...         return self.client
        ...     
        ...     def disconnect(self):
        ...         if self.client:
        ...             self.client.close()
        ...             self.client = None
        ...     
        ...     def fetch_data(self) -> pd.DataFrame:
        ...         if not self.client:
        ...             self.connect()
        ...         return self.client.get_data()
        
        Using with context manager:
        
        >>> with APIConnector("https://api.example.com", "key123") as conn:
        ...     data = conn.fetch_data()
        ...     print(f"Fetched {len(data)} rows")
    """

    @abstractmethod
    def fetch_data(self) -> pd.DataFrame:
        """Fetch data from the underlying source.
        
        This method must be implemented by all concrete connector classes.
        It should return a pandas DataFrame containing the data from the
        configured data source.
        
        Returns:
            DataFrame containing the fetched data.
            
        Raises:
            NotImplementedError: If the subclass doesn't implement this method.
            
        Example:
            >>> class CSVConnector(DataConnector):
            ...     def fetch_data(self) -> pd.DataFrame:
            ...         return pd.read_csv(self.file_path)
        """
        ...

    def connect(self) -> Optional[Any]:
        """Establish connection to data source.
        
        Optional method for connectors that need connection management.
        Override in subclasses that require persistent connections,
        connection pooling, or authentication setup.
        
        Returns:
            Connection object if applicable, None otherwise.
            
        Example:
            >>> def connect(self) -> DatabaseConnection:
            ...     self.connection = DatabaseConnection(
            ...         host=self.host,
            ...         credentials=self.credentials
            ...     )
            ...     return self.connection
        """
        return None

    def disconnect(self) -> None:
        """Clean up connection resources.
        
        Optional method for connectors that need connection management.
        Override in subclasses that require explicit resource cleanup,
        such as closing database connections or releasing file handles.
        
        Example:
            >>> def disconnect(self) -> None:
            ...     if hasattr(self, 'connection') and self.connection:
            ...         self.connection.close()
            ...         self.connection = None
        """
        pass

    def __enter__(self):
        """Context manager entry point.
        
        Automatically calls connect() when entering the context manager.
        This enables automatic connection management with 'with' statements.
        
        Returns:
            Self for chaining operations.
            
        Example:
            >>> with MyConnector(config) as conn:
            ...     data = conn.fetch_data()
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point.
        
        Automatically calls disconnect() when exiting the context manager,
        ensuring proper resource cleanup even if exceptions occur.
        
        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        self.disconnect()

class BaseSourceConfig(BaseModel):
    """Base configuration model for data sources in Slideflow.
    
    This class provides the foundation for all data source configuration models.
    It defines the common fields and behavior that all data sources must implement,
    including type discrimination and connector instantiation.
    
    The configuration system uses Pydantic for validation and type safety, with
    a discriminator pattern to support multiple data source types in a single
    configuration structure.
    
    Key Features:
        - Type discrimination for polymorphic configurations
        - Automatic connector instantiation from configuration
        - Validation of configuration parameters
        - Integration with caching system
        - Strict validation with extra fields forbidden
    
    Required Subclass Implementation:
        Subclasses must define:
        - `type`: String literal for the data source type
        - `connector_class`: Class variable pointing to the connector class
        - Additional fields specific to that data source type
    
    Example:
        Creating a custom configuration:
        
        >>> class APISourceConfig(BaseSourceConfig):
        ...     type: Literal["api"] = "api"
        ...     api_url: str
        ...     api_key: str
        ...     timeout: int = 30
        ...     connector_class = APIConnector
        
        Using the configuration:
        
        >>> config = APISourceConfig(
        ...     name="sales_api",
        ...     type="api",
        ...     api_url="https://api.example.com",
        ...     api_key="secret123"
        ... )
        >>> data = config.fetch_data()
    """
    type: Annotated[str, Field(..., description = "Source type discriminator")]
    name: Annotated[str, Field(..., description = "Logical name for this source")]

    # each subclass overrides this
    connector_class: ClassVar[Type['DataConnector']]

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
    )

    def get_connector(self) -> DataConnector:
        """Instantiate the connector from configuration parameters.
        
        Creates a new instance of the connector class using the configuration
        parameters. Excludes the 'type' and 'name' fields which are used for
        discrimination and identification rather than connection parameters.
        
        Returns:
            New instance of the connector class configured with the
            parameters from this configuration.
            
        Example:
            >>> config = CSVSourceConfig(
            ...     name="sales_data",
            ...     type="csv",
            ...     file_path="/data/sales.csv"
            ... )
            >>> connector = config.get_connector()
            >>> isinstance(connector, CSVConnector)  # True
        """
        # collect only the fields the connector __init__ expects
        kwargs = self.model_dump(
            include = {f for f in self.model_fields if f not in ("type", "name")}
        )
        return self.connector_class(**kwargs)

    def fetch_data(self) -> pd.DataFrame:
        """Fetch data using the configured connector with caching.
        
        Convenience method that instantiates the connector and fetches data
        in a single operation. Integrates with the global caching system to
        avoid redundant data fetching for the same source configuration.
        
        The cache key is generated from all configuration parameters except
        'name', which is used for logical identification rather than data
        source specification.
        
        Returns:
            DataFrame containing the fetched data. Returns cached data if
            available, otherwise fetches fresh data and caches it.
            
        Example:
            >>> config = CSVSourceConfig(
            ...     name="sales_data",
            ...     type="csv", 
            ...     file_path="/data/sales.csv"
            ... )
            >>> data = config.fetch_data()  # Fetches and caches
            >>> data2 = config.fetch_data()  # Returns cached data
        """
        cache = get_data_cache()
        
        cache_kwargs = self.model_dump(
            include = {f for f in self.model_fields if f not in ("name",)}
        )
        
        cached_data = cache.get(source_type = self.type, **cache_kwargs)
        if cached_data is not None:
            return cached_data
        data = self.get_connector().fetch_data()
        cache.set(data, source_type = self.type, **cache_kwargs)
        
        return data
