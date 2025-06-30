import pandas as pd
from pathlib import Path
from pydantic import Field, ConfigDict
from typing import Annotated, Literal, ClassVar, Type

from slideflow.data.connectors.base import DataConnector, BaseSourceConfig
from slideflow.utilities.logging import log_data_operation

class CSVConnector(DataConnector):
    """
    Data connector for reading CSV files.
    """
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def fetch_data(self) -> pd.DataFrame:
        df = pd.read_csv(self.file_path)
        log_data_operation("fetch", "csv", len(df), file_path=self.file_path)
        return df


class CSVSourceConfig(BaseSourceConfig):
    """
    Configuration schema for CSV data sources.
    """
    type: Literal["csv"] = Field("csv", description = "Discriminator: this config reads from a CSV file")
    file_path: Annotated[Path, Field(..., description = "Path to the CSV file")]
    connector_class: ClassVar[Type[DataConnector]] = CSVConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
    )
