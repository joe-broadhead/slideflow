from pydantic import Field
from typing import Annotated, Union

from slideflow.data.connectors.csv import CSVSourceConfig
from slideflow.data.connectors.json import JSONSourceConfig
from slideflow.data.connectors.dbt import DBTDatabricksSourceConfig
from slideflow.data.connectors.databricks import DatabricksSourceConfig

DataSourceConfig = Annotated[
    Union[
        CSVSourceConfig,
        JSONSourceConfig,
        DatabricksSourceConfig,
        DBTDatabricksSourceConfig
    ],
    Field(discriminator = "type"),
]