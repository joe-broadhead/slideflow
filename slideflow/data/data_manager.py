import logging
import pandas as pd
from typing import Dict

from slideflow.data.connectors.base import DataSourceConfig, get_data_connector

logger = logging.getLogger(__name__)

class DataManager:
    """
    A simple data caching manager that fetches and caches data from a given data source.

    This class avoids redundant data fetches by caching previously loaded datasets
    using their `name` attribute as the cache key.
    """

    def __init__(self) -> None:
        """
        Initializes the DataManager with an empty in-memory cache.
        """
        self.data_cache: Dict[str, pd.DataFrame] = {}

    def get_data(self, data_source: DataSourceConfig) -> pd.DataFrame:
        """
        Fetches data from a connector based on the data source configuration.

        If the data has already been fetched, returns the cached version instead
        of performing a new request.

        Args:
            data_source (DataSourceConfig): Configuration describing the data source.

        Returns:
            pd.DataFrame: The retrieved (or cached) data as a Pandas DataFrame.
        """
        key = data_source.name
        if key not in self.data_cache:
            logger.debug(f'Fetching data for source: {key}')
            connector = get_data_connector(data_source)
            self.data_cache[key] = connector.fetch_data()
        else:
            logger.debug(f'Returning cached data for source: {key}')
        return self.data_cache[key]
