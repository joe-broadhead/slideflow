"""DuckDB connector and SQL executor utilities for Slideflow.

This module provides direct DuckDB query execution and a SQL executor for
composable DBT warehouse routing.
"""

import importlib
from typing import Any, ClassVar, Literal, Optional, Type

import pandas as pd
from pydantic import ConfigDict, Field

from slideflow.data.connectors.base import BaseSourceConfig, DataConnector, SQLExecutor
from slideflow.utilities.error_messages import safe_error_line
from slideflow.utilities.exceptions import DataSourceError


def _normalize_file_search_path(
    file_search_path: Optional[str | list[str]],
) -> Optional[str]:
    """Normalize DuckDB file_search_path setting to a comma-separated string."""
    if file_search_path is None:
        return None
    if isinstance(file_search_path, str):
        normalized = file_search_path.strip()
        return normalized or None

    normalized_parts = [part.strip() for part in file_search_path if part.strip()]
    if not normalized_parts:
        return None
    return ",".join(normalized_parts)


class DuckDBConnectorError(DataSourceError):
    """Typed DuckDB connector failure with coarse category metadata."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(f"duckdb[{category}] {message}")


class DuckDBConnector(DataConnector):
    """Execute SQL queries against DuckDB and return pandas DataFrames."""

    def __init__(
        self,
        query: str,
        database: Optional[str] = ":memory:",
        read_only: bool = True,
        file_search_path: Optional[str | list[str]] = None,
    ) -> None:
        self.query = query
        self.database = database or ":memory:"
        self.read_only = read_only
        self.file_search_path = file_search_path
        self._normalized_file_search_path = _normalize_file_search_path(
            file_search_path
        )
        self._connection: Optional[Any] = None
        self._file_search_path_applied = False

    @staticmethod
    def _load_duckdb_module() -> Any:
        """Load duckdb lazily."""
        try:
            return importlib.import_module("duckdb")
        except ImportError as error:  # pragma: no cover - exercised via unit tests
            raise DuckDBConnectorError(
                "configuration",
                "duckdb is required for DuckDB execution. "
                "Install with: pip install slideflow-presentations[duckdb]",
            ) from error

    def connect(self) -> Any:
        """Initialize and cache a DuckDB connection."""
        if self._connection is None:
            duckdb_module = self._load_duckdb_module()
            connect_fn = getattr(duckdb_module, "connect", None)
            if connect_fn is None:  # pragma: no cover - defensive guard
                raise DuckDBConnectorError(
                    "configuration",
                    "duckdb.connect is unavailable in installed duckdb package.",
                )
            try:
                self._connection = connect_fn(
                    database=self.database,
                    read_only=self.read_only,
                )
            except Exception as error:
                raise DuckDBConnectorError(
                    "connection",
                    "Failed to initialize DuckDB connection "
                    f"({safe_error_line(error)})",
                ) from error
        return self._connection

    def disconnect(self) -> None:
        """Release the cached DuckDB connection."""
        connection = self._connection
        self._connection = None
        self._file_search_path_applied = False
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            # Best effort cleanup; keep original fetch/query errors intact.
            pass

    @staticmethod
    def _cursor_to_dataframe(cursor: Any) -> pd.DataFrame:
        """Convert DuckDB cursor/relation results to a pandas DataFrame."""
        for method_name in ("fetch_df", "fetchdf", "df"):
            method = getattr(cursor, method_name, None)
            if callable(method):
                return method()

        fetchall = getattr(cursor, "fetchall", None)
        if callable(fetchall):
            rows = fetchall()
            description = getattr(cursor, "description", None) or []
            columns = [col[0] for col in description] if description else None
            return pd.DataFrame(rows, columns=columns)

        raise DuckDBConnectorError(
            "query",
            "DuckDB query result could not be converted to a DataFrame.",
        )

    def _apply_file_search_path(self, connection: Any) -> None:
        """Apply DuckDB file_search_path setting once per connection."""
        if self._file_search_path_applied:
            return
        if not self._normalized_file_search_path:
            return

        escaped = self._normalized_file_search_path.replace("'", "''")
        try:
            connection.execute(f"SET file_search_path = '{escaped}'")
        except Exception as error:
            raise DuckDBConnectorError(
                "configuration",
                "Failed to set DuckDB file_search_path " f"({safe_error_line(error)})",
            ) from error
        self._file_search_path_applied = True

    def fetch_data(self) -> pd.DataFrame:
        """Execute SQL against DuckDB and return a DataFrame."""
        connection = self.connect()
        self._apply_file_search_path(connection)
        try:
            cursor = connection.execute(self.query)
            return self._cursor_to_dataframe(cursor)
        except DuckDBConnectorError:
            raise
        except Exception as error:
            raise DuckDBConnectorError(
                "query",
                f"Failed to execute DuckDB query ({safe_error_line(error)})",
            ) from error


class DuckDBSQLExecutor(SQLExecutor):
    """SQL executor that runs queries against DuckDB."""

    def __init__(
        self,
        database: Optional[str] = ":memory:",
        read_only: bool = True,
        file_search_path: Optional[str | list[str]] = None,
    ) -> None:
        self.database = database
        self.read_only = read_only
        self.file_search_path = file_search_path

    def execute(self, sql_query: str) -> pd.DataFrame:
        """Execute SQL query text against DuckDB."""
        connector = DuckDBConnector(
            query=sql_query,
            database=self.database,
            read_only=self.read_only,
            file_search_path=self.file_search_path,
        )
        return connector.fetch_data()


class DuckDBSourceConfig(BaseSourceConfig):
    """Configuration model for direct DuckDB SQL sources."""

    type: Literal["duckdb"] = Field("duckdb", description="DuckDB SQL source")
    query: str = Field(..., description="SQL query")
    database: Optional[str] = Field(
        ":memory:",
        description="DuckDB database path or ':memory:'",
    )
    read_only: bool = Field(
        True, description="Open DuckDB connection in read-only mode"
    )
    file_search_path: Optional[str | list[str]] = Field(
        None,
        description=(
            "Optional DuckDB file_search_path setting for resolving relative files. "
            "May be a comma-separated string or list of paths."
        ),
    )

    connector_class: ClassVar[Type[DataConnector]] = DuckDBConnector

    model_config = ConfigDict(extra="forbid")
