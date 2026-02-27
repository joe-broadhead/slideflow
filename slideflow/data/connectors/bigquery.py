"""BigQuery SQL execution connector utilities for Slideflow.

This module provides execution primitives for running SQL queries against
Google BigQuery and returning pandas DataFrames. It is primarily used by
composable DBT sources that compile model SQL and then execute it on a
warehouse backend.

The implementation is intentionally executor-oriented (rather than a full
first-class source config type) so DBT connectors can compose warehouse
execution behavior without duplicating SQL client logic.
"""

import importlib
import json
import os
import time
from typing import Any, Optional

import pandas as pd
from google.auth.exceptions import DefaultCredentialsError

from slideflow.constants import Environment
from slideflow.data.connectors.base import DataConnector, SQLExecutor
from slideflow.utilities.error_messages import safe_error_line
from slideflow.utilities.exceptions import DataSourceError
from slideflow.utilities.logging import (
    get_logger,
    log_api_operation,
    log_data_operation,
)

logger = get_logger(__name__)


class BigQueryConnectorError(DataSourceError):
    """Typed BigQuery connector failure with coarse category metadata."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(f"bigquery[{category}] {message}")


class BigQueryConnector(DataConnector):
    """Execute SQL queries against BigQuery and return pandas DataFrames."""

    def __init__(
        self,
        query: str,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        credentials_json: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ) -> None:
        self.query = query
        self.project_id = project_id
        self.location = location or os.getenv(Environment.BIGQUERY_LOCATION)
        self.credentials_json = credentials_json
        self.credentials_path = credentials_path
        self._client: Optional[Any] = None

    @staticmethod
    def _load_bigquery_client_class() -> Any:
        """Load google.cloud.bigquery.Client lazily."""
        try:
            bigquery_module = importlib.import_module("google.cloud.bigquery")
        except ImportError as error:  # pragma: no cover - exercised via unit tests
            raise BigQueryConnectorError(
                "configuration",
                "google-cloud-bigquery is required for BigQuery execution. "
                "Install with: pip install google-cloud-bigquery",
            ) from error

        client_cls = getattr(bigquery_module, "Client", None)
        if client_cls is None:  # pragma: no cover - defensive guard
            raise BigQueryConnectorError(
                "configuration",
                "google.cloud.bigquery.Client is not available in installed package.",
            )
        return client_cls

    @staticmethod
    def _load_service_account_credentials_class() -> Any:
        """Load google.oauth2.service_account.Credentials lazily."""
        try:
            service_account_module = importlib.import_module(
                "google.oauth2.service_account"
            )
        except ImportError as error:  # pragma: no cover - defensive guard
            raise BigQueryConnectorError(
                "configuration",
                "google-auth is required for BigQuery service account credentials.",
            ) from error

        credentials_cls = getattr(service_account_module, "Credentials", None)
        if credentials_cls is None:  # pragma: no cover - defensive guard
            raise BigQueryConnectorError(
                "configuration",
                "google.oauth2.service_account.Credentials is unavailable.",
            )
        return credentials_cls

    @staticmethod
    def _categorize_error(error: Exception) -> str:
        """Classify BigQuery failures into stable categories."""
        if isinstance(error, DefaultCredentialsError):
            return "authentication"

        message = safe_error_line(error).lower()
        if any(
            token in message
            for token in (
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
        if "project" in message and "not found" in message:
            return "configuration"
        return "query"

    def _categorize_connect_error(self, error: Exception) -> str:
        """Classify connect-time failures while avoiding a false query label."""
        category = self._categorize_error(error)
        return "connection" if category == "query" else category

    def _build_credentials(self) -> tuple[Optional[Any], Optional[str]]:
        """Build explicit credentials (if configured) and infer project id."""
        if self.credentials_json and self.credentials_path:
            raise BigQueryConnectorError(
                "configuration",
                "Provide only one of credentials_json or credentials_path for BigQuery.",
            )

        if self.credentials_json:
            credentials_cls = self._load_service_account_credentials_class()
            try:
                payload = json.loads(self.credentials_json)
            except json.JSONDecodeError as error:
                raise BigQueryConnectorError(
                    "configuration",
                    "BigQuery credentials_json is not valid JSON.",
                ) from error

            try:
                credentials = credentials_cls.from_service_account_info(payload)
            except Exception as error:
                raise BigQueryConnectorError(
                    "configuration",
                    "Failed to load BigQuery credentials from credentials_json "
                    f"({safe_error_line(error)})",
                ) from error

            inferred_project = payload.get("project_id") or getattr(
                credentials, "project_id", None
            )
            return credentials, inferred_project

        if self.credentials_path:
            credentials_cls = self._load_service_account_credentials_class()
            try:
                credentials = credentials_cls.from_service_account_file(
                    self.credentials_path
                )
            except Exception as error:
                raise BigQueryConnectorError(
                    "configuration",
                    "Failed to load BigQuery credentials from credentials_path "
                    f"({safe_error_line(error)})",
                ) from error

            inferred_project = getattr(credentials, "project_id", None)
            return credentials, inferred_project

        return None, None

    def connect(self) -> Any:
        """Initialize and cache a BigQuery client."""
        if self._client is None:
            credentials, inferred_project = self._build_credentials()
            project_id = (
                self.project_id
                or inferred_project
                or os.getenv(Environment.BIGQUERY_PROJECT)
                or os.getenv(Environment.GOOGLE_CLOUD_PROJECT)
            )
            if not project_id:
                raise BigQueryConnectorError(
                    "configuration",
                    "Missing BigQuery project id. Set warehouse.project_id or "
                    "BIGQUERY_PROJECT/GOOGLE_CLOUD_PROJECT.",
                )

            client_kwargs: dict[str, Any] = {"project": project_id}
            if self.location:
                client_kwargs["location"] = self.location
            if credentials is not None:
                client_kwargs["credentials"] = credentials

            client_cls = self._load_bigquery_client_class()
            try:
                self._client = client_cls(**client_kwargs)
            except BigQueryConnectorError:
                raise
            except Exception as error:
                category = self._categorize_connect_error(error)
                raise BigQueryConnectorError(
                    category,
                    "Failed to initialize BigQuery client "
                    f"({safe_error_line(error)})",
                ) from error
        return self._client

    def disconnect(self) -> None:
        """Release the cached BigQuery client reference."""
        client = self._client
        self._client = None
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                logger.debug("BigQuery client close failed; ignoring.", exc_info=True)

    def fetch_data(self) -> pd.DataFrame:
        """Execute SQL against BigQuery and return a DataFrame."""
        start_time = time.time()
        try:
            client = self.connect()
            query_start = time.time()
            if self.location:
                query_job = client.query(self.query, location=self.location)
            else:
                query_job = client.query(self.query)
            result_df = query_job.to_dataframe()
            query_duration = time.time() - query_start

            total_duration = time.time() - start_time
            log_api_operation(
                "bigquery",
                "sql_query",
                True,
                query_duration,
                query_length=len(self.query),
            )
            log_data_operation(
                "fetch",
                "bigquery",
                len(result_df),
                total_duration=total_duration,
                query_duration=query_duration,
            )
            return result_df
        except Exception as error:
            duration = time.time() - start_time
            wrapped_error = (
                error
                if isinstance(error, BigQueryConnectorError)
                else BigQueryConnectorError(
                    self._categorize_error(error),
                    f"BigQuery query failed ({safe_error_line(error)})",
                )
            )
            log_api_operation(
                "bigquery",
                "sql_query",
                False,
                duration,
                error=str(wrapped_error),
                query_length=len(self.query),
            )
            if wrapped_error is error:
                raise wrapped_error
            raise wrapped_error from error


class BigQuerySQLExecutor(SQLExecutor):
    """SQL executor that runs queries against BigQuery."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        credentials_json: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        self.project_id = project_id
        self.location = location
        self.credentials_json = credentials_json
        self.credentials_path = credentials_path

    def execute(self, sql_query: str) -> pd.DataFrame:
        """Execute SQL via BigQueryConnector and return DataFrame results."""
        return BigQueryConnector(
            sql_query,
            project_id=self.project_id,
            location=self.location,
            credentials_json=self.credentials_json,
            credentials_path=self.credentials_path,
        ).fetch_data()
