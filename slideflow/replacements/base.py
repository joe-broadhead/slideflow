"""Base class and interface for all replacement types in Slideflow.

This module defines the abstract base class that all replacement implementations
must inherit from. It provides common functionality for data fetching,
transformation, and the interface contract that enables polymorphic usage
of different replacement types.

The base class integrates with:
    - Data transformation pipeline for preprocessing
    - Pydantic validation for type safety
    - Discriminated unions for automatic type selection

Example:
    Creating a custom replacement type:
    
    >>> from slideflow.replacements.base import BaseReplacement
    >>> from typing import Literal
    >>> 
    >>> class MyCustomReplacement(BaseReplacement):
    ...     type: Literal["custom"] = "custom"
    ...     custom_field: str
    ...     
    ...     def get_replacement(self) -> str:
    ...         # Custom replacement logic here
    ...         data = self.fetch_data()
    ...         if data is not None:
    ...             data = self.apply_data_transforms(data)
    ...         return f"Custom: {self.custom_field}"
"""

import pandas as pd
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from slideflow.utilities.data_transforms import apply_data_transforms

class BaseReplacement(BaseModel):
    """Abstract base class for all text replacement implementations.
    
    This class provides the common interface and functionality that all
    replacement types must implement. It handles data transformation,
    provides hooks for data fetching, and establishes the type discrimination
    pattern used throughout the replacement system.
    
    The base class is designed to work with Pydantic's discriminated union
    system, allowing automatic instantiation of the correct replacement type
    based on the 'type' field in configuration data.
    
    Subclasses must implement:
        - get_replacement(): Core method that produces the replacement content
        - Optionally override fetch_data(): For custom data retrieval logic
    
    Attributes:
        type: String identifier used for discriminated union type selection.
        data_transforms: Optional list of transformation operations to apply
            to fetched data before processing.
            
    Example:
        Implementing a custom replacement:
        
        >>> class WeatherReplacement(BaseReplacement):
        ...     type: Literal["weather"] = "weather"
        ...     location: str
        ...     api_key: str
        ...     
        ...     def get_replacement(self) -> str:
        ...         # Fetch weather data for location
        ...         weather_data = fetch_weather(self.location, self.api_key)
        ...         return f"Weather in {self.location}: {weather_data['temperature']}°F"
        
        Using with discriminated unions:
        
        >>> # Configuration automatically creates correct type
        >>> config = {
        ...     "type": "weather",
        ...     "location": "New York",
        ...     "api_key": "secret_key"
        ... }
        >>> replacement = ReplacementUnion.validate(config)
        >>> content = replacement.get_replacement()
    """
    type: str = Field(..., description = "Discriminator for replacement type")
    data_transforms: Optional[List[Dict[str, Any]]] = Field(
        default = None, 
        description = "Optional data transformations to apply (resolved by ConfigLoader)"
    )

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
        arbitrary_types_allowed = True
    )

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """Fetch data from external sources for this replacement.
        
        This method provides a hook for subclasses to implement custom data
        fetching logic. The base implementation returns None, indicating no
        data source is configured. Subclasses that need to fetch data from
        databases, APIs, or files should override this method.
        
        The fetched data is typically used in get_replacement() after being
        processed through apply_data_transforms().
        
        Returns:
            DataFrame containing the fetched data if a data source is configured,
            None if no data fetching is needed for this replacement type.
            
        Example:
            Custom data fetching implementation:
            
            >>> class DatabaseReplacement(BaseReplacement):
            ...     database_query: str
            ...     connection_string: str
            ...     
            ...     def fetch_data(self) -> Optional[pd.DataFrame]:
            ...         import sqlalchemy as sa
            ...         engine = sa.create_engine(self.connection_string)
            ...         return pd.read_sql(self.database_query, engine)
            ...     
            ...     def get_replacement(self) -> str:
            ...         data = self.fetch_data()
            ...         if data is not None:
            ...             data = self.apply_data_transforms(data)
            ...             return f"Records found: {len(data)}"
            ...         return "No data available"
        """
        return None
    
    def apply_data_transforms(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply configured data transformations to a DataFrame.
        
        This method delegates to the shared data transformation system to apply
        any configured preprocessing operations like filtering, aggregation,
        calculations, or formatting to the input DataFrame.
        
        The transformations are applied in the order specified in the
        data_transforms configuration list. If no transformations are configured,
        the DataFrame is returned unchanged.
        
        Args:
            df: Input DataFrame to transform.
            
        Returns:
            Transformed DataFrame with all configured operations applied.
            
        Example:
            Using data transformations:
            
            >>> replacement = MyReplacement(
            ...     type="my_type",
            ...     data_transforms=[
            ...         {"type": "filter", "column": "status", "value": "active"},
            ...         {"type": "aggregate", "column": "revenue", "operation": "sum"}
            ...     ]
            ... )
            >>> raw_data = pd.DataFrame({"status": ["active", "inactive"], "revenue": [100, 50]})
            >>> transformed = replacement.apply_data_transforms(raw_data)
            >>> # Result: filtered to active records, revenue summed
        """
        return apply_data_transforms(self.data_transforms, df)
