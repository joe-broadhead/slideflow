import os
import logging
import pandas as pd
from databricks import sql
from pydantic import Field
from typing import Annotated, Literal

from slideflow.data.connectors.common import DataConnector, BaseSourceConfig

logger = logging.getLogger(__name__)

class DatabricksSQLConnector(DataConnector):
    """
    Data connector for executing SQL queries against a Databricks cluster.

    Attributes:
        query (str): SQL query string to execute on Databricks.
    """
    def __init__(self, query: str):
        """
        Initializes the DatabricksSQLConnector with a SQL query.

        Args:
            query (str): SQL query to be executed on Databricks.
        """
        self.query = query

    def get_databricks_connection(self):
        """
        Establishes a connection to the Databricks cluster using environment variables.

        Required environment variables:
            - DATABRICKS_HOST: The Databricks workspace hostname.
            - HTTP_PATH: The HTTP path to the SQL endpoint.
            - DBT_ACCESS_TOKEN: The access token for authentication.

        Returns:
            databricks.sql.connect: An active Databricks connection.
        """
        return sql.connect(
            server_hostname = os.getenv('DATABRICKS_HOST'),
            http_path = os.getenv('HTTP_PATH'),
            access_token = os.getenv('DBT_ACCESS_TOKEN')
        )

    def fetch_data(self) -> pd.DataFrame:
        """
        Executes the SQL query on Databricks and returns the result as a pandas DataFrame.

        Returns:
            pd.DataFrame: The query results.
        """
        with self.get_databricks_connection() as conn:
            with conn.cursor() as cursor:
                logger.info(f'Fetching data from Databricks SQL')
                cursor.execute(self.query)
                return cursor.fetchall_arrow().to_pandas()

class DatabricksSourceConfig(BaseSourceConfig):
    """
    Configuration schema for Databricks data sources.

    Attributes:
        type (str): The source type, always 'databricks'.
        query (str): The SQL query string to execute.
    """
    type: Literal['databricks'] = Field('databricks', description = 'Databricks data source.')
    query: Annotated[str, Field(description = 'SQL query to run on Databricks.')]
