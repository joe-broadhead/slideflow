import pandas as pd
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated, ClassVar, Type, Any, Optional

from slideflow.data.cache import get_data_cache

class DataConnector(ABC):
    """
    Abstract base class for all data connectors.
    Subclasses must override `fetch_data()` to return a DataFrame.
    """

    @abstractmethod
    def fetch_data(self) -> pd.DataFrame:
        """
        Fetches data from the underlying source.
        """
        ...

    def connect(self) -> Optional[Any]:
        """
        Establish connection to data source.
        Override in subclasses that need connection management.
        Returns connection object or None if not applicable.
        """
        return None

    def disconnect(self) -> None:
        """
        Clean up connection resources.
        Override in subclasses that need connection management.
        """
        pass

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

class BaseSourceConfig(BaseModel):
    """
    Base model for a data‐source configuration.
    Subclasses must set `type` (the discriminator) and `connector_class`.
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
        """
        Instantiate the connector by passing all
        the remaining fields (besides type & name)
        into `connector_class(...)`.
        """
        # collect only the fields the connector __init__ expects
        kwargs = self.model_dump(
            include = {f for f in self.model_fields if f not in ("type", "name")}
        )
        return self.connector_class(**kwargs)

    def fetch_data(self) -> pd.DataFrame:
        """
        Shortcut: instantiate & fetch in one go.
        Uses global cache to avoid re-fetching the same data.
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
