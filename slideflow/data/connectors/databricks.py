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
from typing import Annotated, Any, ClassVar, Literal, Optional, Type

import pandas as pd
from pydantic import ConfigDict, Field

from slideflow.citations import CitationEntry, fingerprint_text
from slideflow.constants import Defaults, Environment
from slideflow.data.connectors.base import BaseSourceConfig, DataConnector, SQLExecutor
from slideflow.utilities.error_messages import safe_error_line
from slideflow.utilities.exceptions import DataSourceError
from slideflow.utilities.logging import (
    get_logger,
    log_api_operation,
    log_data_operation,
)

logger = get_logger(__name__)

try:
    from databricks import sql as _databricks_sql
except ImportError:  # pragma: no cover - exercised in optional-dependency tests
    _databricks_sql = None

# Keep a module-level symbol for test monkeypatching and compatibility.
sql = _databricks_sql


def _resolve_positive_float_from_env(env_var: str, default: float) -> float:
    """Resolve a positive float from env with safe fallback."""
    raw_value = os.getenv(env_var)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _resolve_positive_int_from_env(env_var: str, default: int) -> int:
    """Resolve a positive int from env with safe fallback."""
    raw_value = os.getenv(env_var)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _require_databricks_sql_module() -> Any:
    """Return databricks.sql module or raise actionable install guidance."""
    if sql is None:
        raise DatabricksConnectorError(
            "configuration",
            "databricks-sql-connector is required for Databricks sources. "
            "Install with: pip install slideflow-presentations[databricks]",
        )
    return sql


class DatabricksConnectorError(DataSourceError):
    """Typed Databricks connector failure with coarse category metadata."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(f"databricks[{category}] {message}")


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

    def __init__(
        self,
        query: str,
        socket_timeout_s: Optional[float] = None,
        retry_max_attempts: Optional[int] = None,
        retry_max_duration_s: Optional[float] = None,
        retry_delay_min_s: Optional[float] = None,
        retry_delay_max_s: Optional[float] = None,
    ) -> None:
        """Initialize the Databricks connector.

        Args:
            query: SQL query to execute against the Databricks cluster.
                Should be a valid SQL statement that returns tabular data.
        """
        self.query = query
        self._connection: Optional[Any] = None
        self.socket_timeout_s = (
            socket_timeout_s
            if socket_timeout_s is not None
            else _resolve_positive_float_from_env(
                Environment.SLIDEFLOW_DATABRICKS_SOCKET_TIMEOUT_S,
                Defaults.DATABRICKS_SOCKET_TIMEOUT_S,
            )
        )
        self.retry_max_attempts = (
            retry_max_attempts
            if retry_max_attempts is not None
            else _resolve_positive_int_from_env(
                Environment.SLIDEFLOW_DATABRICKS_RETRY_MAX_ATTEMPTS,
                Defaults.DATABRICKS_RETRY_MAX_ATTEMPTS,
            )
        )
        self.retry_max_duration_s = (
            retry_max_duration_s
            if retry_max_duration_s is not None
            else _resolve_positive_float_from_env(
                Environment.SLIDEFLOW_DATABRICKS_RETRY_MAX_DURATION_S,
                Defaults.DATABRICKS_RETRY_MAX_DURATION_S,
            )
        )
        self.retry_delay_min_s = (
            retry_delay_min_s
            if retry_delay_min_s is not None
            else _resolve_positive_float_from_env(
                Environment.SLIDEFLOW_DATABRICKS_RETRY_DELAY_MIN_S,
                Defaults.DATABRICKS_RETRY_DELAY_MIN_S,
            )
        )
        self.retry_delay_max_s = (
            retry_delay_max_s
            if retry_delay_max_s is not None
            else _resolve_positive_float_from_env(
                Environment.SLIDEFLOW_DATABRICKS_RETRY_DELAY_MAX_S,
                Defaults.DATABRICKS_RETRY_DELAY_MAX_S,
            )
        )
        if self.retry_delay_max_s < self.retry_delay_min_s:
            self.retry_delay_max_s = self.retry_delay_min_s

    @staticmethod
    def _categorize_error(error: Exception) -> str:
        """Classify Databricks execution failures into stable categories."""
        message = safe_error_line(error).lower()
        if any(
            token in message
            for token in (
                "token",
                "credential",
                "authentication",
                "unauthorized",
                "forbidden",
                "permission",
            )
        ):
            return "authentication"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if any(
            token in message
            for token in ("connect", "connection", "network", "dns", "unreachable")
        ):
            return "network"
        return "query"

    def _categorize_connect_error(self, error: Exception) -> str:
        """Classify connect-time failures while avoiding a false query label."""
        category = self._categorize_error(error)
        return "connection" if category == "query" else category

    @staticmethod
    def _get_databricks_credentials() -> tuple[str, str, str]:
        """Read and validate required Databricks auth env vars."""
        required = (
            Environment.DATABRICKS_HOST,
            Environment.DATABRICKS_HTTP_PATH,
            Environment.DATABRICKS_ACCESS_TOKEN,
        )
        values: dict[str, str] = {}
        missing: list[str] = []
        for env_var in required:
            value = os.getenv(env_var)
            if value is None or not value.strip():
                missing.append(env_var)
                continue
            values[env_var] = value

        if missing:
            missing_display = ", ".join(missing)
            raise DatabricksConnectorError(
                "configuration",
                f"Missing required environment variable(s): {missing_display}",
            )

        return (
            values[Environment.DATABRICKS_HOST],
            values[Environment.DATABRICKS_HTTP_PATH],
            values[Environment.DATABRICKS_ACCESS_TOKEN],
        )

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
            host, http_path, access_token = self._get_databricks_credentials()
            try:
                databricks_sql = _require_databricks_sql_module()
                self._connection = databricks_sql.connect(
                    server_hostname=host,
                    http_path=http_path,
                    access_token=access_token,
                    user_agent_entry="Slideflow",
                    _socket_timeout=self.socket_timeout_s,
                    _retry_stop_after_attempts_count=self.retry_max_attempts,
                    _retry_stop_after_attempts_duration=self.retry_max_duration_s,
                    _retry_delay_min=self.retry_delay_min_s,
                    _retry_delay_max=self.retry_delay_max_s,
                )
            except DatabricksConnectorError:
                raise
            except Exception as error:
                category = self._categorize_connect_error(error)
                raise DatabricksConnectorError(
                    category,
                    f"Failed to connect to Databricks ({safe_error_line(error)})",
                ) from error
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
                    query_length=len(self.query),
                )
                log_data_operation(
                    "fetch",
                    "databricks",
                    len(result_df),
                    total_duration=total_duration,
                    query_duration=query_duration,
                )
                return result_df
        except Exception as e:
            duration = time.time() - start_time
            wrapped_error = (
                e
                if isinstance(e, DatabricksConnectorError)
                else DatabricksConnectorError(
                    self._categorize_error(e),
                    f"Databricks query failed ({safe_error_line(e)})",
                )
            )
            log_api_operation(
                "databricks",
                "sql_query",
                False,
                duration,
                error=str(wrapped_error),
                query_length=len(self.query),
            )
            raise wrapped_error from e


class DatabricksSQLExecutor(SQLExecutor):
    """SQL executor that runs queries against Databricks warehouses."""

    def execute(self, sql_query: str) -> pd.DataFrame:
        """Execute SQL via DatabricksConnector and return DataFrame results."""
        return DatabricksConnector(sql_query).fetch_data()


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

    type: Literal["databricks"] = Field(
        "databricks",
        description="Discriminator: this config runs a Databricks SQL query",
    )
    query: Annotated[
        str, Field(..., description="The SQL query to execute on Databricks")
    ]
    socket_timeout_s: Annotated[
        Optional[float],
        Field(
            default=None,
            gt=0,
            description="Optional Databricks socket timeout override in seconds",
        ),
    ] = None
    retry_max_attempts: Annotated[
        Optional[int],
        Field(
            default=None,
            ge=1,
            description="Optional retry-attempt cap override for transient Databricks failures",
        ),
    ] = None
    retry_max_duration_s: Annotated[
        Optional[float],
        Field(
            default=None,
            gt=0,
            description="Optional retry-duration cap override in seconds",
        ),
    ] = None
    retry_delay_min_s: Annotated[
        Optional[float],
        Field(
            default=None,
            gt=0,
            description="Optional minimum retry delay override in seconds",
        ),
    ] = None
    retry_delay_max_s: Annotated[
        Optional[float],
        Field(
            default=None,
            gt=0,
            description="Optional maximum retry delay override in seconds",
        ),
    ] = None

    connector_class: ClassVar[Type[DataConnector]] = DatabricksConnector

    model_config = ConfigDict(extra="forbid")

    def get_citation_entries(
        self, mode: str = "model", include_query_text: bool = False
    ) -> list[CitationEntry]:
        del mode
        query_fingerprint = fingerprint_text(self.query)
        workspace_host = os.getenv(Environment.DATABRICKS_HOST)
        http_path = os.getenv(Environment.DATABRICKS_HTTP_PATH)
        source_id = f"databricks:{self.name}:{query_fingerprint}"
        metadata: dict[str, Any] = {"query_fingerprint": query_fingerprint}
        if workspace_host:
            metadata["workspace_host"] = workspace_host
        if http_path:
            metadata["warehouse_http_path"] = http_path
        if include_query_text:
            metadata["query_text"] = self.query

        return [
            CitationEntry(
                source_id=source_id,
                provider="databricks",
                display_name=f"{self.name} (databricks query)",
                query_fingerprint=query_fingerprint,
                metadata=metadata,
            )
        ]
