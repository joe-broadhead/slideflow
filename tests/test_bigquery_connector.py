import pandas as pd
import pytest
from pydantic import ValidationError

import slideflow.data.connectors.bigquery as bigquery_module
import slideflow.data.connectors.dbt as dbt_module
from slideflow.utilities.exceptions import DataSourceError


def test_bigquery_connector_connect_uses_explicit_project_and_location(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_bigquery_client_class",
        staticmethod(lambda: FakeClient),
    )
    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_service_account_credentials_class",
        staticmethod(lambda: object()),
    )

    connector = bigquery_module.BigQueryConnector(
        "SELECT 1", project_id="explicit-project", location="US"
    )
    client = connector.connect()

    assert isinstance(client, FakeClient)
    assert captured["project"] == "explicit-project"
    assert captured["location"] == "US"


def test_bigquery_connector_connect_uses_project_env_fallback(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_bigquery_client_class",
        staticmethod(lambda: FakeClient),
    )
    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_service_account_credentials_class",
        staticmethod(lambda: object()),
    )
    monkeypatch.setenv("BIGQUERY_PROJECT", "env-project")

    connector = bigquery_module.BigQueryConnector("SELECT 1")
    connector.connect()

    assert captured["project"] == "env-project"


def test_bigquery_connector_connect_fails_with_missing_project(monkeypatch):
    monkeypatch.delenv("BIGQUERY_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_service_account_credentials_class",
        staticmethod(lambda: object()),
    )

    connector = bigquery_module.BigQueryConnector("SELECT 1")

    with pytest.raises(DataSourceError, match="Missing BigQuery project id"):
        connector.connect()


def test_bigquery_connector_uses_credentials_json_and_infers_project(monkeypatch):
    captured = {}

    class FakeCredentials:
        project_id = "project-from-credentials"

    class FakeCredentialsFactory:
        @staticmethod
        def from_service_account_info(payload):
            assert payload["client_email"] == "svc@example.com"
            return FakeCredentials()

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_service_account_credentials_class",
        staticmethod(lambda: FakeCredentialsFactory),
    )
    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_bigquery_client_class",
        staticmethod(lambda: FakeClient),
    )

    connector = bigquery_module.BigQueryConnector(
        "SELECT 1",
        credentials_json='{"client_email":"svc@example.com","project_id":"project-from-json"}',
    )
    connector.connect()

    assert captured["project"] == "project-from-json"
    assert isinstance(captured["credentials"], FakeCredentials)


def test_bigquery_connector_fetch_data_returns_dataframe(monkeypatch):
    captured = {}

    class FakeQueryJob:
        def to_dataframe(self):
            return pd.DataFrame({"value": [1]})

    class FakeClient:
        def __init__(self, **kwargs):
            captured["init_kwargs"] = kwargs

        def query(self, query, location=None):
            captured["query"] = query
            captured["location"] = location
            return FakeQueryJob()

    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_bigquery_client_class",
        staticmethod(lambda: FakeClient),
    )
    monkeypatch.setattr(
        bigquery_module.BigQueryConnector,
        "_load_service_account_credentials_class",
        staticmethod(lambda: object()),
    )

    connector = bigquery_module.BigQueryConnector(
        "SELECT 1", project_id="project", location="EU"
    )
    result = connector.fetch_data()

    assert result.to_dict(orient="records") == [{"value": 1}]
    assert captured["query"] == "SELECT 1"
    assert captured["location"] == "EU"


def test_bigquery_sql_executor_delegates_to_connector(monkeypatch):
    captured = {}

    class ConnectorStub:
        def __init__(
            self,
            query,
            project_id=None,
            location=None,
            credentials_json=None,
            credentials_path=None,
        ):
            captured["query"] = query
            captured["project_id"] = project_id
            captured["location"] = location
            captured["credentials_json"] = credentials_json
            captured["credentials_path"] = credentials_path

        def fetch_data(self):
            return pd.DataFrame({"value": [42]})

    monkeypatch.setattr(bigquery_module, "BigQueryConnector", ConnectorStub)

    executor = bigquery_module.BigQuerySQLExecutor(
        project_id="project", location="US", credentials_path="/tmp/key.json"
    )
    result = executor.execute("SELECT 42")

    assert captured["query"] == "SELECT 42"
    assert captured["project_id"] == "project"
    assert captured["location"] == "US"
    assert captured["credentials_json"] is None
    assert captured["credentials_path"] == "/tmp/key.json"
    assert result.to_dict(orient="records") == [{"value": 42}]


def test_dbt_source_config_resolves_to_bigquery_connector():
    config = dbt_module.DBTSourceConfig(
        name="metrics",
        type="dbt",
        model_alias="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
        },
        warehouse={
            "type": "bigquery",
            "project_id": "project",
            "location": "US",
            "credentials_path": "/tmp/key.json",
        },
    )

    connector = config.get_connector()
    assert isinstance(connector, dbt_module.DBTBigQueryConnector)
    assert connector.project_id == "project"
    assert connector.location == "US"
    assert connector.credentials_path == "/tmp/key.json"


def test_dbt_source_config_rejects_unsupported_warehouse():
    with pytest.raises(ValidationError, match="Input should be"):
        dbt_module.DBTSourceConfig(
            name="metrics",
            type="dbt",
            model_alias="metrics_model",
            dbt={
                "package_url": "https://github.com/org/repo.git",
                "project_dir": "/tmp/workspace",
            },
            warehouse={"type": "snowflake"},
        )


def test_dbt_bigquery_connector_executes_compiled_sql(monkeypatch):
    captured = {}

    class ManifestStub:
        def __init__(self, **_kwargs):
            pass

        def get_compiled_query(self, model_alias, **selectors):
            captured["model_alias"] = model_alias
            captured["selectors"] = selectors
            return "SELECT 7 AS answer"

    class ExecutorStub:
        def __init__(self, project_id=None, location=None, **kwargs):
            captured["project_id"] = project_id
            captured["location"] = location
            captured["credentials_json"] = kwargs.get("credentials_json")
            captured["credentials_path"] = kwargs.get("credentials_path")

        def execute(self, sql_query):
            captured["sql_query"] = sql_query
            return pd.DataFrame({"answer": [7]})

    monkeypatch.setattr(dbt_module, "DBTManifestConnector", ManifestStub)
    monkeypatch.setattr(dbt_module, "BigQuerySQLExecutor", ExecutorStub)

    connector = dbt_module.DBTBigQueryConnector(
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        project_id="project",
        location="US",
        credentials_path="/tmp/key.json",
    )

    result = connector.fetch_data()

    assert result.to_dict(orient="records") == [{"answer": 7}]
    assert captured["model_alias"] == "metrics_model"
    assert captured["selectors"] == {
        "model_unique_id": "model.pkg.metrics_model",
        "model_package_name": "pkg",
        "model_selector_name": "metrics_model",
    }
    assert captured["project_id"] == "project"
    assert captured["location"] == "US"
    assert captured["credentials_path"] == "/tmp/key.json"
    assert captured["sql_query"] == "SELECT 7 AS answer"
