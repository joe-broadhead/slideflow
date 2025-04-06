import logging
import pandas as pd
from pydantic import Field
from typing import Annotated, Literal

from slideflow.data.connectors.common import DataConnector, BaseSourceConfig

logger = logging.getLogger(__name__)

class CSVConnector(DataConnector):
    """
    Data connector for reading CSV files.

    Attributes:
        file_path (str): Path to the CSV file.
    """
    def __init__(self, file_path: str):
        """
        Initializes the CSVConnector with the given file path.

        Args:
            file_path (str): Path to the CSV file.
        """
        self.file_path = file_path

    def fetch_data(self) -> pd.DataFrame:
        """
        Loads the CSV file into a pandas DataFrame.

        Returns:
            pd.DataFrame: The loaded data.
        """
        logger.info(f'Fetching data from CSV: {self.file_path}')
        return pd.read_csv(self.file_path)

class CSVSourceConfig(BaseSourceConfig):
    """
    Configuration schema for CSV data sources.

    Attributes:
        type (str): The source type, always 'csv'.
        file_path (str): Path to the CSV file.
    """
    type: Literal['csv'] = Field('csv', description = 'CSV data source.')
    file_path: Annotated[str, Field(description = 'Path to the CSV file.')]
