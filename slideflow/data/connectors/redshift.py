"""Amazon Redshift connector and SQL executor utilities for Slideflow."""

import os
import time
from importlib import import_module
from typing import Any, ClassVar, Literal, Optional, Type

import pandas as pd
from pydantic import ConfigDict, Field

from slideflow.citations import CitationEntry, fingerprint_text
from slideflow.constants import Defaults, Environment
from slideflow.data.connectors.base import BaseSourceConfig, DataConnector, SQLExecutor
from slideflow.utilities.error_messages import redacted_error_line, safe_error_line
from slideflow.utilities.exceptions import DataSourceError
from slideflow.utilities.logging import log_api_operation, log_data_operation

try:
    _imported_redshift_connector: Any = import_module("redshift_connector")
except ImportError:  # pragma: no cover - exercised in optional-dependency tests
    _imported_redshift_connector = None

# Module-level symbol keeps optional dependency import lazy and testable.
redshift_connector: Any = _imported_redshift_connector


def _clean_optional_string(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = value.strip()
    return clean or None


def _first_env(*env_names: str) -> Optional[str]:
    for env_name in env_names:
        value = _clean_optional_string(os.getenv(env_name))
        if value:
            return value
    return None


def _resolve_string(value: Optional[str], *env_names: str) -> Optional[str]:
    return _clean_optional_string(value) or _first_env(*env_names)


def _resolve_bool(
    value: Optional[bool],
    env_name: str,
    *,
    default: bool,
) -> bool:
    if value is not None:
        return value
    raw_value = _clean_optional_string(os.getenv(env_name))
    if raw_value is None:
        return default
    return raw_value.lower() in {"1", "true", "yes", "on"}


def _resolve_int(
    value: Optional[int],
    env_name: str,
    *,
    default: Optional[int] = None,
) -> Optional[int]:
    if value is not None:
        return value
    raw_value = _clean_optional_string(os.getenv(env_name))
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _require_redshift_connector_module() -> Any:
    """Return redshift_connector module or raise actionable install guidance."""
    if redshift_connector is None:
        raise RedshiftConnectorError(
            "configuration",
            "redshift-connector is required for Redshift sources. "
            "Install with: pip install slideflow-presentations[redshift]",
        )
    return redshift_connector


class RedshiftConnectorError(DataSourceError):
    """Typed Redshift connector failure with coarse category metadata."""

    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(f"redshift[{category}] {message}")


class RedshiftConnector(DataConnector):
    """Execute SQL queries against Amazon Redshift and return DataFrames."""

    def __init__(
        self,
        query: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        iam: Optional[bool] = None,
        db_user: Optional[str] = None,
        cluster_identifier: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
        is_serverless: Optional[bool] = None,
        serverless_acct_id: Optional[str] = None,
        serverless_work_group: Optional[str] = None,
        ssl: Optional[bool] = None,
        sslmode: Optional[str] = None,
        timeout: Optional[int] = None,
        application_name: Optional[str] = None,
        connection_options: Optional[dict[str, Any]] = None,
    ) -> None:
        self.query = query
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.iam = iam
        self.db_user = db_user
        self.cluster_identifier = cluster_identifier
        self.region = region
        self.profile = profile
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.session_token = session_token
        self.is_serverless = is_serverless
        self.serverless_acct_id = serverless_acct_id
        self.serverless_work_group = serverless_work_group
        self.ssl = ssl
        self.sslmode = sslmode
        self.timeout = timeout
        self.application_name = application_name
        self.connection_options = dict(connection_options or {})
        self._connection: Optional[Any] = None

    @staticmethod
    def _categorize_error(error: Exception) -> str:
        """Classify Redshift execution failures into stable categories."""
        message = safe_error_line(error).lower()
        if any(
            token in message
            for token in (
                "password",
                "credential",
                "authentication",
                "authorization",
                "unauthorized",
                "forbidden",
                "permission",
                "access denied",
                "invalid user",
                "iam",
                "token",
            )
        ):
            return "authentication"
        if "timeout" in message or "timed out" in message:
            return "timeout"
        if any(
            token in message
            for token in (
                "connect",
                "connection",
                "network",
                "dns",
                "unreachable",
                "could not translate host",
                "name resolution",
            )
        ):
            return "network"
        return "query"

    def _categorize_connect_error(self, error: Exception) -> str:
        """Classify connect-time failures while avoiding a false query label."""
        category = self._categorize_error(error)
        return "connection" if category == "query" else category

    def _build_connection_kwargs(self) -> dict[str, Any]:
        iam = _resolve_bool(self.iam, Environment.REDSHIFT_IAM, default=False)
        ssl = _resolve_bool(self.ssl, Environment.REDSHIFT_SSL, default=True)
        serverless_acct_id = _resolve_string(
            self.serverless_acct_id, Environment.REDSHIFT_SERVERLESS_ACCT_ID
        )
        serverless_work_group = _resolve_string(
            self.serverless_work_group, Environment.REDSHIFT_SERVERLESS_WORK_GROUP
        )
        is_serverless = self.is_serverless
        if is_serverless is None:
            is_serverless = bool(serverless_acct_id or serverless_work_group)

        kwargs: dict[str, Any] = {
            "host": _resolve_string(self.host, Environment.REDSHIFT_HOST),
            "port": _resolve_int(
                self.port,
                Environment.REDSHIFT_PORT,
                default=Defaults.REDSHIFT_PORT,
            ),
            "database": _resolve_string(self.database, Environment.REDSHIFT_DATABASE),
            "user": _resolve_string(self.user, Environment.REDSHIFT_USER),
            "password": _resolve_string(self.password, Environment.REDSHIFT_PASSWORD),
            "iam": iam,
            "db_user": _resolve_string(self.db_user, Environment.REDSHIFT_DB_USER),
            "cluster_identifier": _resolve_string(
                self.cluster_identifier,
                Environment.REDSHIFT_CLUSTER_IDENTIFIER,
            ),
            "region": _resolve_string(
                self.region,
                Environment.REDSHIFT_REGION,
                Environment.AWS_REGION,
                Environment.AWS_DEFAULT_REGION,
            ),
            "profile": _resolve_string(
                self.profile,
                Environment.REDSHIFT_PROFILE,
                Environment.AWS_PROFILE,
            ),
            "access_key_id": _resolve_string(
                self.access_key_id,
                Environment.REDSHIFT_ACCESS_KEY_ID,
                Environment.AWS_ACCESS_KEY_ID,
            ),
            "secret_access_key": _resolve_string(
                self.secret_access_key,
                Environment.REDSHIFT_SECRET_ACCESS_KEY,
                Environment.AWS_SECRET_ACCESS_KEY,
            ),
            "session_token": _resolve_string(
                self.session_token,
                Environment.REDSHIFT_SESSION_TOKEN,
                Environment.AWS_SESSION_TOKEN,
            ),
            "is_serverless": is_serverless,
            "serverless_acct_id": serverless_acct_id,
            "serverless_work_group": serverless_work_group,
            "ssl": ssl,
            "sslmode": _resolve_string(self.sslmode, Environment.REDSHIFT_SSLMODE),
            "timeout": _resolve_int(self.timeout, Environment.REDSHIFT_TIMEOUT),
            "application_name": _resolve_string(self.application_name)
            or Defaults.CLIENT_USER_AGENT,
        }
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        kwargs.update(self.connection_options)
        self._validate_connection_kwargs(kwargs)
        return kwargs

    @staticmethod
    def _validate_connection_kwargs(kwargs: dict[str, Any]) -> None:
        if not kwargs.get("database"):
            raise RedshiftConnectorError(
                "configuration",
                "Missing Redshift database. Set database or REDSHIFT_DATABASE.",
            )

        if kwargs.get("iam"):
            if not (
                kwargs.get("host")
                or kwargs.get("cluster_identifier")
                or (
                    kwargs.get("serverless_acct_id")
                    and kwargs.get("serverless_work_group")
                )
            ):
                raise RedshiftConnectorError(
                    "configuration",
                    "IAM Redshift connections require host, cluster_identifier, "
                    "or serverless_acct_id plus serverless_work_group.",
                )
            if not kwargs.get("region"):
                raise RedshiftConnectorError(
                    "configuration",
                    "IAM Redshift connections require region or AWS_REGION/AWS_DEFAULT_REGION.",
                )
            return

        missing = [
            field_name
            for field_name in ("host", "user", "password")
            if not kwargs.get(field_name)
        ]
        if missing:
            missing_display = ", ".join(missing)
            raise RedshiftConnectorError(
                "configuration",
                "Missing required Redshift connection field(s): "
                f"{missing_display}. Set config fields or REDSHIFT_* env vars.",
            )

    def connect(self) -> Any:
        """Initialize and cache a Redshift connection."""
        if self._connection is None:
            redshift_module = _require_redshift_connector_module()
            connect_fn = getattr(redshift_module, "connect", None)
            if connect_fn is None:  # pragma: no cover - defensive guard
                raise RedshiftConnectorError(
                    "configuration",
                    "redshift_connector.connect is unavailable in installed package.",
                )
            try:
                self._connection = connect_fn(**self._build_connection_kwargs())
            except RedshiftConnectorError:
                raise
            except Exception as error:
                category = self._categorize_connect_error(error)
                raise RedshiftConnectorError(
                    category,
                    "Failed to connect to Redshift " f"({redacted_error_line(error)})",
                ) from error
        return self._connection

    def disconnect(self) -> None:
        """Release the cached Redshift connection."""
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                # Best-effort cleanup; keep original query errors intact.
                pass

    @staticmethod
    def _cursor_to_dataframe(cursor: Any) -> pd.DataFrame:
        """Convert Redshift cursor results to a pandas DataFrame."""
        fetch_dataframe = getattr(cursor, "fetch_dataframe", None)
        if callable(fetch_dataframe):
            return fetch_dataframe()

        fetchall = getattr(cursor, "fetchall", None)
        if callable(fetchall):
            rows = fetchall()
            description = getattr(cursor, "description", None) or []
            if description:
                columns = [column[0] for column in description]
                return pd.DataFrame([dict(zip(columns, row)) for row in rows])
            return pd.DataFrame(rows)

        raise RedshiftConnectorError(
            "query",
            "Redshift query result could not be converted to a DataFrame.",
        )

    def fetch_data(self) -> pd.DataFrame:
        """Execute SQL against Redshift and return a DataFrame."""
        start_time = time.time()
        try:
            connection = self.connect()
            cursor = connection.cursor()
            try:
                query_start = time.time()
                cursor.execute(self.query)
                result_df = self._cursor_to_dataframe(cursor)
                query_duration = time.time() - query_start
            finally:
                close_cursor = getattr(cursor, "close", None)
                if callable(close_cursor):
                    close_cursor()

            total_duration = time.time() - start_time
            log_api_operation(
                "redshift",
                "sql_query",
                True,
                query_duration,
                query_length=len(self.query),
            )
            log_data_operation(
                "fetch",
                "redshift",
                len(result_df),
                total_duration=total_duration,
                query_duration=query_duration,
            )
            return result_df
        except Exception as error:
            duration = time.time() - start_time
            wrapped_error = (
                error
                if isinstance(error, RedshiftConnectorError)
                else RedshiftConnectorError(
                    self._categorize_error(error),
                    f"Redshift query failed ({redacted_error_line(error)})",
                )
            )
            log_api_operation(
                "redshift",
                "sql_query",
                False,
                duration,
                error=str(wrapped_error),
                query_length=len(self.query),
            )
            if wrapped_error is error:
                raise wrapped_error
            raise wrapped_error from error


class RedshiftSQLExecutor(SQLExecutor):
    """SQL executor that runs queries against Amazon Redshift."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        iam: Optional[bool] = None,
        db_user: Optional[str] = None,
        cluster_identifier: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
        is_serverless: Optional[bool] = None,
        serverless_acct_id: Optional[str] = None,
        serverless_work_group: Optional[str] = None,
        ssl: Optional[bool] = None,
        sslmode: Optional[str] = None,
        timeout: Optional[int] = None,
        application_name: Optional[str] = None,
        connection_options: Optional[dict[str, Any]] = None,
    ) -> None:
        self.connection_kwargs: dict[str, Any] = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "iam": iam,
            "db_user": db_user,
            "cluster_identifier": cluster_identifier,
            "region": region,
            "profile": profile,
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
            "session_token": session_token,
            "is_serverless": is_serverless,
            "serverless_acct_id": serverless_acct_id,
            "serverless_work_group": serverless_work_group,
            "ssl": ssl,
            "sslmode": sslmode,
            "timeout": timeout,
            "application_name": application_name,
            "connection_options": connection_options,
        }

    def execute(self, sql_query: str) -> pd.DataFrame:
        """Execute SQL via RedshiftConnector and return DataFrame results."""
        return RedshiftConnector(sql_query, **self.connection_kwargs).fetch_data()


class RedshiftSourceConfig(BaseSourceConfig):
    """Configuration model for direct Amazon Redshift SQL sources."""

    type: Literal["redshift"] = Field("redshift", description="Redshift SQL source")
    query: str = Field(..., description="SQL query")
    host: Optional[str] = Field(None, description="Redshift cluster host")
    port: Optional[int] = Field(
        None, ge=1, le=65535, description="Redshift port; defaults to 5439"
    )
    database: Optional[str] = Field(None, description="Redshift database")
    user: Optional[str] = Field(None, description="Database user")
    password: Optional[str] = Field(None, description="Database password")
    iam: Optional[bool] = Field(None, description="Use Redshift IAM authentication")
    db_user: Optional[str] = Field(None, description="IAM db_user override")
    cluster_identifier: Optional[str] = Field(
        None, description="Redshift cluster identifier for IAM auth"
    )
    region: Optional[str] = Field(None, description="AWS region")
    profile: Optional[str] = Field(None, description="AWS profile name")
    access_key_id: Optional[str] = Field(None, description="AWS access key id")
    secret_access_key: Optional[str] = Field(None, description="AWS secret access key")
    session_token: Optional[str] = Field(None, description="AWS session token")
    is_serverless: Optional[bool] = Field(
        None, description="Use Redshift Serverless endpoint resolution"
    )
    serverless_acct_id: Optional[str] = Field(
        None, description="Redshift Serverless account id"
    )
    serverless_work_group: Optional[str] = Field(
        None, description="Redshift Serverless workgroup"
    )
    ssl: Optional[bool] = Field(
        None, description="Enable SSL; defaults to true when omitted"
    )
    sslmode: Optional[str] = Field(None, description="Redshift SSL mode")
    timeout: Optional[int] = Field(None, gt=0, description="Connection timeout seconds")
    application_name: Optional[str] = Field(
        None, description="Redshift application_name; defaults to Slideflow"
    )
    connection_options: dict[str, Any] = Field(
        default_factory=dict,
        description="Advanced redshift_connector.connect options",
    )

    connector_class: ClassVar[Type[DataConnector]] = RedshiftConnector

    model_config = ConfigDict(extra="forbid")

    def get_citation_entries(
        self, mode: str = "model", include_query_text: bool = False
    ) -> list[CitationEntry]:
        del mode
        query_fingerprint = fingerprint_text(self.query)
        endpoint = self.host or self.cluster_identifier or self.serverless_work_group
        source_id = f"redshift:{self.name}:{query_fingerprint}"
        metadata: dict[str, Any] = {
            "query_fingerprint": query_fingerprint,
            "database": self.database,
            "host": endpoint,
            "port": self.port or Defaults.REDSHIFT_PORT,
            "iam": self.iam,
            "is_serverless": self.is_serverless,
        }
        if include_query_text:
            metadata["query_text"] = self.query
        return [
            CitationEntry(
                source_id=source_id,
                provider="redshift",
                display_name=f"{self.name} (redshift query)",
                query_fingerprint=query_fingerprint,
                metadata=metadata,
            )
        ]
