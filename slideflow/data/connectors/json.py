import pandas as pd
from pathlib import Path
from pydantic import Field, ConfigDict
from typing import Annotated, Literal, ClassVar, Type

from slideflow.data.connectors.base import DataConnector, BaseSourceConfig
from slideflow.utilities.logging import log_data_operation
from slideflow.constants import Defaults

class JSONConnector(DataConnector):
    """
    Data connector for reading JSON files into pandas DataFrames.
    """
    def __init__(self, file_path: str, orient: str = Defaults.JSON_ORIENT) -> None:
        self.file_path = file_path
        self.orient = orient

    def fetch_data(self) -> pd.DataFrame:
        df = pd.read_json(self.file_path, orient = self.orient)
        log_data_operation("fetch", "json", len(df), file_path=self.file_path, orient=self.orient)
        return df

class JSONSourceConfig(BaseSourceConfig):
    """
    Configuration schema for JSON data sources.
    """
    type: Literal["json"] = Field("json", description = "Discriminator: this config reads from a JSON file")
    file_path: Annotated[Path, Field(..., description = "Path to the JSON file")]
    orient: Annotated[str, Field(default = Defaults.JSON_ORIENT, description = "`orient` parameter passed to pandas.read_json")]
    connector_class: ClassVar[Type[DataConnector]] = JSONConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
    )
