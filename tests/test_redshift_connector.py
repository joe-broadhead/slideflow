from types import SimpleNamespace

import pandas as pd
import pytest

import slideflow.data.connectors.dbt as dbt_module
import slideflow.data.connectors.redshift as redshift_module
from slideflow.utilities.exceptions import DataSourceError


def _fake_redshift_module(connect_fn):
    return SimpleNamespace(connect=connect_fn)


def _clear_redshift_env(monkeypatch):
    for env_name in (
        "REDSHIFT_HOST",
        "REDSHIFT_PORT",
        "REDSHIFT_DATABASE",
        "REDSHIFT_USER",
        "REDSHIFT_PASSWORD",
        "REDSHIFT_IAM",
        "REDSHIFT_DB_USER",
        "REDSHIFT_CLUSTER_IDENTIFIER",
        "REDSHIFT_REGION",
        "REDSHIFT_PROFILE",
        "REDSHIFT_ACCESS_KEY_ID",
        "REDSHIFT_SECRET_ACCESS_KEY",
        "REDSHIFT_SESSION_TOKEN",
        "REDSHIFT_SERVERLESS_ACCT_ID",
        "REDSHIFT_SERVERLESS_WORK_GROUP",
        "REDSHIFT_SSL",
        "REDSHIFT_SSLMODE",
        "REDSHIFT_TIMEOUT",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    ):
        monkeypatch.delenv(env_name, raising=False)


def test_redshift_missing_dependency_has_actionable_message(monkeypatch):
    monkeypatch.setattr(redshift_module, "redshift_connector", None)

    connector = redshift_module.RedshiftConnector(
        "SELECT 1",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )

    with pytest.raises(DataSourceError, match=r"slideflow-presentations\[redshift\]"):
        connector.connect()


def test_redshift_connect_uses_explicit_non_iam_config(monkeypatch):
    _clear_redshift_env(monkeypatch)
    captured = {}

    class FakeConnection:
        pass

    def _connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(
        redshift_module, "redshift_connector", _fake_redshift_module(_connect)
    )

    connector = redshift_module.RedshiftConnector(
        "SELECT 1",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
        connection_options={"numeric_to_float": True},
    )
    connection = connector.connect()

    assert isinstance(connection, FakeConnection)
    assert captured["host"] == "redshift.example.com"
    assert captured["port"] == 5439
    assert captured["database"] == "analytics"
    assert captured["user"] == "report_user"
    assert captured["password"] == "secret"
    assert captured["ssl"] is True
    assert captured["iam"] is False
    assert captured["application_name"] == "Slideflow"
    assert captured["numeric_to_float"] is True


def test_redshift_connect_uses_env_fallbacks(monkeypatch):
    _clear_redshift_env(monkeypatch)
    captured = {}

    def _connect(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        redshift_module, "redshift_connector", _fake_redshift_module(_connect)
    )
    monkeypatch.setenv("REDSHIFT_HOST", "env-redshift.example.com")
    monkeypatch.setenv("REDSHIFT_PORT", "15439")
    monkeypatch.setenv("REDSHIFT_DATABASE", "env_analytics")
    monkeypatch.setenv("REDSHIFT_USER", "env_user")
    monkeypatch.setenv("REDSHIFT_PASSWORD", "env_password")
    monkeypatch.setenv("REDSHIFT_SSL", "false")
    monkeypatch.setenv("REDSHIFT_TIMEOUT", "30")

    redshift_module.RedshiftConnector("SELECT 1").connect()

    assert captured["host"] == "env-redshift.example.com"
    assert captured["port"] == 15439
    assert captured["database"] == "env_analytics"
    assert captured["user"] == "env_user"
    assert captured["password"] == "env_password"
    assert captured["ssl"] is False
    assert captured["timeout"] == 30


def test_redshift_connect_supports_iam_serverless(monkeypatch):
    _clear_redshift_env(monkeypatch)
    captured = {}

    def _connect(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        redshift_module, "redshift_connector", _fake_redshift_module(_connect)
    )

    connector = redshift_module.RedshiftConnector(
        "SELECT 1",
        database="analytics",
        iam=True,
        region="eu-west-1",
        db_user="iam_user",
        serverless_acct_id="123456789012",
        serverless_work_group="analytics-wg",
        profile="analytics-profile",
    )
    connector.connect()

    assert captured["iam"] is True
    assert captured["is_serverless"] is True
    assert captured["region"] == "eu-west-1"
    assert captured["db_user"] == "iam_user"
    assert captured["serverless_acct_id"] == "123456789012"
    assert captured["serverless_work_group"] == "analytics-wg"
    assert captured["profile"] == "analytics-profile"
    assert "password" not in captured


def test_redshift_connect_validates_required_fields(monkeypatch):
    _clear_redshift_env(monkeypatch)
    monkeypatch.setattr(
        redshift_module,
        "redshift_connector",
        _fake_redshift_module(lambda **_kwargs: object()),
    )

    with pytest.raises(DataSourceError, match="Missing Redshift database"):
        redshift_module.RedshiftConnector("SELECT 1").connect()

    with pytest.raises(DataSourceError, match="host, user, password"):
        redshift_module.RedshiftConnector(
            "SELECT 1",
            database="analytics",
        ).connect()

    with pytest.raises(DataSourceError, match="IAM Redshift connections require"):
        redshift_module.RedshiftConnector(
            "SELECT 1",
            database="analytics",
            iam=True,
            region="eu-west-1",
        ).connect()


def test_redshift_fetch_data_prefers_fetch_dataframe(monkeypatch):
    captured = {"closed": False}

    class FakeCursor:
        def execute(self, query):
            captured["query"] = query

        @staticmethod
        def fetch_dataframe():
            return pd.DataFrame({"value": [1]})

        def close(self):
            captured["closed"] = True

    class FakeConnection:
        @staticmethod
        def cursor():
            return FakeCursor()

    connector = redshift_module.RedshiftConnector(
        "SELECT 1",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )
    monkeypatch.setattr(connector, "connect", lambda: FakeConnection())

    result = connector.fetch_data()

    assert result.to_dict(orient="records") == [{"value": 1}]
    assert captured["query"] == "SELECT 1"
    assert captured["closed"] is True


def test_redshift_fetch_data_falls_back_to_fetchall(monkeypatch):
    class FakeCursor:
        description = [("value",)]

        def execute(self, query):
            self.query = query

        @staticmethod
        def fetchall():
            return [(7,)]

    class FakeConnection:
        @staticmethod
        def cursor():
            return FakeCursor()

    connector = redshift_module.RedshiftConnector(
        "SELECT 7",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )
    monkeypatch.setattr(connector, "connect", lambda: FakeConnection())

    result = connector.fetch_data()

    assert result.to_dict(orient="records") == [{"value": 7}]


def test_redshift_error_categories(monkeypatch):
    _clear_redshift_env(monkeypatch)

    def _connect(**_kwargs):
        raise RuntimeError("password authentication failed")

    monkeypatch.setattr(
        redshift_module, "redshift_connector", _fake_redshift_module(_connect)
    )

    connector = redshift_module.RedshiftConnector(
        "SELECT 1",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )

    with pytest.raises(redshift_module.RedshiftConnectorError) as exc_info:
        connector.connect()

    assert exc_info.value.category == "authentication"
    assert str(exc_info.value).startswith("redshift[authentication]")
    assert "secret" not in str(exc_info.value)


def test_redshift_disconnect_closes_connection():
    closed = {"value": False}

    class FakeConnection:
        def close(self):
            closed["value"] = True

    connector = redshift_module.RedshiftConnector(
        "SELECT 1",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )
    connector._connection = FakeConnection()

    connector.disconnect()

    assert closed["value"] is True
    assert connector._connection is None


def test_redshift_sql_executor_delegates_to_connector(monkeypatch):
    captured = {}

    class ConnectorStub:
        def __init__(self, query, **kwargs):
            captured["query"] = query
            captured["kwargs"] = kwargs

        @staticmethod
        def fetch_data():
            return pd.DataFrame({"value": [42]})

    monkeypatch.setattr(redshift_module, "RedshiftConnector", ConnectorStub)

    executor = redshift_module.RedshiftSQLExecutor(
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
        timeout=30,
    )
    result = executor.execute("SELECT 42")

    assert captured["query"] == "SELECT 42"
    assert captured["kwargs"]["host"] == "redshift.example.com"
    assert captured["kwargs"]["database"] == "analytics"
    assert captured["kwargs"]["timeout"] == 30
    assert result.to_dict(orient="records") == [{"value": 42}]


def test_redshift_source_config_get_connector():
    config = redshift_module.RedshiftSourceConfig(
        name="redshift_metrics",
        type="redshift",
        query="SELECT 1",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )

    connector = config.get_connector()

    assert isinstance(connector, redshift_module.RedshiftConnector)
    assert connector.host == "redshift.example.com"
    assert connector.database == "analytics"


def test_dbt_source_config_resolves_to_redshift_connector():
    config = dbt_module.DBTSourceConfig(
        name="metrics",
        type="dbt",
        model_alias="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
        },
        warehouse={
            "type": "redshift",
            "host": "redshift.example.com",
            "database": "analytics",
            "user": "report_user",
            "password": "secret",
            "ssl": True,
        },
    )

    connector = config.get_connector()

    assert isinstance(connector, dbt_module.DBTRedshiftConnector)
    assert connector.host == "redshift.example.com"
    assert connector.database == "analytics"
    assert connector.user == "report_user"
    assert connector.ssl is True


def test_dbt_redshift_connector_executes_compiled_sql(monkeypatch):
    captured = {}

    class ManifestStub:
        def __init__(self, **_kwargs):
            pass

        def get_compiled_query(self, model_alias, **selectors):
            captured["model_alias"] = model_alias
            captured["selectors"] = selectors
            return "SELECT 9 AS answer"

    class ExecutorStub:
        def __init__(self, **kwargs):
            captured["executor_kwargs"] = kwargs

        def execute(self, sql_query):
            captured["sql_query"] = sql_query
            return pd.DataFrame({"answer": [9]})

    monkeypatch.setattr(dbt_module, "DBTManifestConnector", ManifestStub)
    monkeypatch.setattr(dbt_module, "RedshiftSQLExecutor", ExecutorStub)

    connector = dbt_module.DBTRedshiftConnector(
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        host="redshift.example.com",
        database="analytics",
        user="report_user",
        password="secret",
    )

    result = connector.fetch_data()

    assert result.to_dict(orient="records") == [{"answer": 9}]
    assert captured["model_alias"] == "metrics_model"
    assert captured["selectors"] == {
        "model_unique_id": "model.pkg.metrics_model",
        "model_package_name": "pkg",
        "model_selector_name": "metrics_model",
    }
    assert captured["executor_kwargs"]["host"] == "redshift.example.com"
    assert captured["executor_kwargs"]["database"] == "analytics"
    assert captured["sql_query"] == "SELECT 9 AS answer"
