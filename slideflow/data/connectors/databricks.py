import os
import time
import pandas as pd
from databricks import sql
from pydantic import Field, ConfigDict
from typing import Annotated, Literal, ClassVar, Type

from slideflow.data.connectors.base import DataConnector, BaseSourceConfig
from slideflow.utilities.logging import get_logger, log_data_operation, log_api_operation

logger = get_logger(__name__)

class DatabricksConnector(DataConnector):
    """
    Data connector for executing SQL queries against a Databricks cluster.
    """
    def __init__(self, query: str) -> None:
        self.query = query
        self._connection = None

    def connect(self):
        """
        Establishes a connection to the Databricks cluster using env vars
        """
        if self._connection is None:
            self._connection = sql.connect(
                server_hostname = os.getenv("DATABRICKS_HOST"),
                http_path = os.getenv("DATABRICKS_HTTP_PATH"),
                access_token = os.getenv("DATABRICKS_ACCESS_TOKEN"),
            )
        return self._connection

    def disconnect(self) -> None:
        """
        Clean up connection resources.
        """
        if self._connection:
            self._connection.close()
            self._connection = None

    def fetch_data(self) -> pd.DataFrame:
        """
        Executes the SQL query and returns a pandas DataFrame.
        """
        start_time = time.time()
        try:
            with self.connect() as conn, conn.cursor() as cursor:
                query_start = time.time()
                cursor.execute(self.query)
                result_df = cursor.fetchall_arrow().to_pandas()
                query_duration = time.time() - query_start
                
                total_duration = time.time() - start_time
                log_api_operation("databricks", "sql_query", True, query_duration, 
                                query_length=len(self.query))
                log_data_operation("fetch", "databricks", len(result_df), 
                                 total_duration=total_duration, query_duration=query_duration)
                return result_df
        except Exception as e:
            duration = time.time() - start_time
            log_api_operation("databricks", "sql_query", False, duration, 
                            error=str(e), query_length=len(self.query))
            raise


class DatabricksSourceConfig(BaseSourceConfig):
    """
    Configuration schema for Databricks data sources.
    """
    type: Literal["databricks"] = Field("databricks", description = "Discriminator: this config runs a Databricks SQL query")
    query: Annotated[str, Field(..., description = "The SQL query to execute on Databricks")]

    connector_class: ClassVar[Type[DataConnector]] = DatabricksConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type"
    )
