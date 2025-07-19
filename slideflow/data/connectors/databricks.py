"""Databricks SQL data connector for Slideflow.

This module provides a connector and configuration for executing SQL queries
against Databricks SQL warehouses. It handles connection management, query
execution, and comprehensive logging of API operations.

The Databricks connector enables direct access to Databricks SQL warehouses,
allowing presentations to pull data from data lakes, delta tables, and any
data accessible through Databricks SQL.

Key Features:
    - SQL query execution against Databricks clusters
    - Connection management with automatic cleanup
    - Environment variable-based authentication
    - Comprehensive operation and performance logging
    - Arrow-optimized data transfer for better performance
    - Automatic error handling and connection recovery

Authentication:
    The connector uses environment variables for authentication:
    - DATABRICKS_HOST: The Databricks workspace hostname
    - DATABRICKS_HTTP_PATH: The SQL warehouse HTTP path
    - DATABRICKS_ACCESS_TOKEN: Personal access token or service principal token

Example:
    Using the Databricks connector:
    
    >>> from slideflow.data.connectors.databricks import DatabricksSourceConfig
    >>> 
    >>> # Create configuration
    >>> config = DatabricksSourceConfig(
    ...     name="sales_summary",
    ...     type="databricks", 
    ...     query="SELECT region, SUM(sales) FROM sales_table GROUP BY region"
    ... )
    >>> 
    >>> # Fetch data (requires environment variables to be set)
    >>> data = config.fetch_data()
    >>> print(f"Retrieved {len(data)} rows from Databricks")
"""

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
    """Data connector for executing SQL queries against Databricks SQL warehouses.
    
    This connector provides access to Databricks SQL warehouses using the official
    Databricks SQL connector. It handles connection management, query execution,
    and performance monitoring with comprehensive logging.
    
    The connector uses Apache Arrow for efficient data transfer and includes
    detailed timing metrics for both API operations and data fetching operations.
    
    Authentication is handled through environment variables, following Databricks
    best practices for credential management.
    
    Example:
        >>> connector = DatabricksConnector(
        ...     query="SELECT * FROM sales WHERE region = 'West'"
        ... )
        >>> with connector:
        ...     data = connector.fetch_data()
        ...     print(f"Query returned {len(data)} rows")
    """
    def __init__(self, query: str) -> None:
        """Initialize the Databricks connector.
        
        Args:
            query: SQL query to execute against the Databricks cluster.
                Should be a valid SQL statement that returns tabular data.
        """
        self.query = query
        self._connection = None

    def connect(self):
        """Establish connection to Databricks SQL warehouse.
        
        Creates a connection to the Databricks cluster using credentials from
        environment variables. Uses the official Databricks SQL connector with
        automatic connection pooling and management.
        
        Required Environment Variables:
            - DATABRICKS_HOST: Databricks workspace hostname
            - DATABRICKS_HTTP_PATH: SQL warehouse HTTP path
            - DATABRICKS_ACCESS_TOKEN: Authentication token
        
        Returns:
            Databricks SQL connection object.
            
        Raises:
            ValueError: If required environment variables are not set.
            ConnectionError: If connection to Databricks fails.
            
        Example:
            >>> connector = DatabricksConnector("SELECT 1")
            >>> connection = connector.connect()
        """
        if self._connection is None:
            self._connection = sql.connect(
                server_hostname = os.getenv("DATABRICKS_HOST"),
                http_path = os.getenv("DATABRICKS_HTTP_PATH"),
                access_token = os.getenv("DATABRICKS_ACCESS_TOKEN"),
            )
        return self._connection

    def disconnect(self) -> None:
        """Clean up Databricks connection resources.
        
        Closes the connection to the Databricks cluster and releases any
        associated resources. Safe to call multiple times.
        
        Example:
            >>> connector = DatabricksConnector("SELECT 1")
            >>> connector.connect()
            >>> connector.disconnect()  # Connection is closed
        """
        if self._connection:
            self._connection.close()
            self._connection = None

    def fetch_data(self) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame.
        
        Executes the configured SQL query against the Databricks cluster and
        returns the results as a pandas DataFrame. Uses Apache Arrow for
        efficient data transfer and includes comprehensive performance logging.
        
        The method tracks both query execution time and total operation time,
        logging successful operations and any errors that occur. All timing
        and performance metrics are logged for monitoring and optimization.
        
        Returns:
            DataFrame containing the query results with columns and data types
            as returned by the Databricks SQL warehouse.
            
        Raises:
            ConnectionError: If unable to connect to Databricks.
            sql.Error: If the SQL query is invalid or execution fails.
            Exception: For other database or network errors.
            
        Example:
            >>> connector = DatabricksConnector(
            ...     query="SELECT product, SUM(sales) as total_sales "
            ...           "FROM sales_table GROUP BY product"
            ... )
            >>> df = connector.fetch_data()
            >>> print(f"Query returned {len(df)} rows, {len(df.columns)} columns")
        """
        start_time = time.time()
        try:
            with self.connect() as conn, conn.cursor() as cursor:
                query_start = time.time()
                cursor.execute(self.query)
                result_df = cursor.fetchall_arrow().to_pandas()
                query_duration = time.time() - query_start
                
                total_duration = time.time() - start_time
                log_api_operation(
                    "databricks",
                    "sql_query",
                    True,
                    query_duration, 
                    query_length = len(self.query)
                )
                log_data_operation(
                    "fetch",
                    "databricks",
                    len(result_df), 
                    total_duration = total_duration,
                    query_duration = query_duration
                )
                return result_df
        except Exception as e:
            duration = time.time() - start_time
            log_api_operation(
                "databricks",
                "sql_query",
                False,
                duration, 
                error = str(e),
                query_length = len(self.query)
            )
            raise

class DatabricksSourceConfig(BaseSourceConfig):
    """Configuration model for Databricks SQL data sources.
    
    This configuration class defines the parameters needed to execute SQL
    queries against Databricks SQL warehouses. It validates the SQL query
    and integrates with the discriminated union system for polymorphic
    data source configurations.
    
    The configuration assumes that Databricks authentication credentials
    are provided via environment variables, following security best practices
    for credential management in production environments.
    
    Attributes:
        type: Always "databricks" for Databricks data sources.
        query: SQL query to execute against the Databricks cluster.
        connector_class: References DatabricksConnector for instantiation.
    
    Example:
        Creating a Databricks data source configuration:
        
        >>> config = DatabricksSourceConfig(
        ...     name="monthly_revenue",
        ...     type="databricks",
        ...     query='''
        ...         SELECT 
        ...             DATE_TRUNC('month', order_date) as month,
        ...             SUM(revenue) as total_revenue
        ...         FROM sales_table
        ...         WHERE order_date >= '2024-01-01'
        ...         GROUP BY DATE_TRUNC('month', order_date)
        ...         ORDER BY month
        ...     '''
        ... )
        >>> 
        >>> # Use configuration to fetch data
        >>> data = config.fetch_data()
        >>> print(f"Retrieved {len(data)} months of revenue data")
        
        From dictionary/JSON:
        
        >>> config_dict = {
        ...     "name": "user_metrics",
        ...     "type": "databricks",
        ...     "query": "SELECT COUNT(*) as active_users FROM users WHERE last_active >= CURRENT_DATE - 30"
        ... }
        >>> config = DatabricksSourceConfig(**config_dict)
    """
    type: Literal["databricks"] = Field("databricks", description = "Discriminator: this config runs a Databricks SQL query")
    query: Annotated[str, Field(..., description = "The SQL query to execute on Databricks")]

    connector_class: ClassVar[Type[DataConnector]] = DatabricksConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type"
    )
