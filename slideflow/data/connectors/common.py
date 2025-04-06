import pandas as pd
from typing import Annotated
from pydantic import BaseModel, Field

class DataConnector:
    """
    Abstract base class for all data connectors.

    All custom connectors should inherit from this class and implement
    the `fetch_data` method to return a pandas DataFrame from the data source.
    """

    def fetch_data(self) -> pd.DataFrame:
        raise NotImplementedError('Subclasses must implement fetch_data().')


class BaseSourceConfig(BaseModel):
    """
    Fetches data from the connector's source.

    This method must be implemented by subclasses.

    Returns:
        pd.DataFrame: The retrieved data.

    Raises:
        NotImplementedError: Always, unless overridden by a subclass.
    """

    type: Annotated[str, Field(description = 'The type of data source.')]
    name: Annotated[str, Field(description = 'The name of the data source.')]

    model_config = {
        'discriminator': 'type'
    }
