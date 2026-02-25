from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

import slideflow.data.connectors.dbt as dbt_module
import slideflow.data.connectors.duckdb as duckdb_module


def test_duckdb_connector_connect_uses_database_and_read_only(monkeypatch):
    captured = {}

    class FakeConnection:
        def execute(self, _sql):
            return SimpleNamespace(fetch_df=lambda: pd.DataFrame({"value": [1]}))

    class FakeDuckDB:
        @staticmethod
        def connect(*, database, read_only):
            captured["database"] = database
            captured["read_only"] = read_only
            return FakeConnection()

    monkeypatch.setattr(
        duckdb_module.DuckDBConnector,
        "_load_duckdb_module",
        staticmethod(lambda: FakeDuckDB),
    )

    connector = duckdb_module.DuckDBConnector(
        query="SELECT 1",
        database="/tmp/example.duckdb",
        read_only=False,
    )
    connector.connect()

    assert captured["database"] == "/tmp/example.duckdb"
    assert captured["read_only"] is False


def test_duckdb_connector_fetch_data_applies_file_search_path_once(monkeypatch):
    executed_sql: list[str] = []
    closed = {"value": False}

    class FakeCursor:
        @staticmethod
        def fetch_df():
            return pd.DataFrame({"value": [1]})

    class FakeConnection:
        def execute(self, sql):
            executed_sql.append(sql)
            return FakeCursor()

        def close(self):
            closed["value"] = True

    class FakeDuckDB:
        @staticmethod
        def connect(*, database, read_only):
            assert database == ":memory:"
            assert read_only is True
            return FakeConnection()

    monkeypatch.setattr(
        duckdb_module.DuckDBConnector,
        "_load_duckdb_module",
        staticmethod(lambda: FakeDuckDB),
    )

    connector = duckdb_module.DuckDBConnector(
        query="SELECT 1 AS value",
        file_search_path=["/data/base", "/data/shared"],
    )

    first = connector.fetch_data()
    second = connector.fetch_data()
    connector.disconnect()

    assert first.to_dict(orient="records") == [{"value": 1}]
    assert second.to_dict(orient="records") == [{"value": 1}]
    assert executed_sql[0] == "SET file_search_path = '/data/base,/data/shared'"
    assert executed_sql[1] == "SELECT 1 AS value"
    assert executed_sql[2] == "SELECT 1 AS value"
    assert closed["value"] is True


def test_duckdb_sql_executor_delegates_to_connector(monkeypatch):
    captured = {}

    class ConnectorStub:
        def __init__(
            self,
            query,
            database=None,
            read_only=True,
            file_search_path=None,
        ):
            captured["query"] = query
            captured["database"] = database
            captured["read_only"] = read_only
            captured["file_search_path"] = file_search_path

        def fetch_data(self):
            return pd.DataFrame({"value": [7]})

    monkeypatch.setattr(duckdb_module, "DuckDBConnector", ConnectorStub)

    executor = duckdb_module.DuckDBSQLExecutor(
        database="/tmp/example.duckdb",
        read_only=False,
        file_search_path="/data",
    )
    result = executor.execute("SELECT 7 AS value")

    assert captured["query"] == "SELECT 7 AS value"
    assert captured["database"] == "/tmp/example.duckdb"
    assert captured["read_only"] is False
    assert captured["file_search_path"] == "/data"
    assert result.to_dict(orient="records") == [{"value": 7}]


def test_duckdb_source_config_defaults():
    config = duckdb_module.DuckDBSourceConfig(
        name="duck",
        type="duckdb",
        query="SELECT 1",
    )

    connector = config.get_connector()

    assert isinstance(connector, duckdb_module.DuckDBConnector)
    assert connector.database == ":memory:"
    assert connector.read_only is True
    assert connector.file_search_path is None


def test_dbt_source_config_resolves_to_duckdb_connector():
    config = dbt_module.DBTSourceConfig(
        name="metrics",
        type="dbt",
        model_alias="metrics_model",
        dbt={
            "package_url": "https://github.com/org/repo.git",
            "project_dir": "/tmp/workspace",
        },
        warehouse={
            "type": "duckdb",
            "database": "/tmp/warehouse.duckdb",
            "read_only": False,
            "file_search_path": ["/tmp/workspace"],
        },
    )

    connector = config.get_connector()
    assert isinstance(connector, dbt_module.DBTDuckDBConnector)
    assert connector.database == "/tmp/warehouse.duckdb"
    assert connector.read_only is False
    assert connector.file_search_path == ["/tmp/workspace"]


def test_dbt_source_config_duckdb_requires_database():
    with pytest.raises(
        ValidationError,
        match="warehouse.database is required when warehouse.type is 'duckdb'",
    ):
        dbt_module.DBTSourceConfig(
            name="metrics",
            type="dbt",
            model_alias="metrics_model",
            dbt={
                "package_url": "https://github.com/org/repo.git",
                "project_dir": "/tmp/workspace",
            },
            warehouse={"type": "duckdb"},
        )


def test_dbt_duckdb_connector_executes_compiled_sql(monkeypatch):
    captured = {}

    class ManifestStub:
        def __init__(self, **_kwargs):
            pass

        def get_compiled_query(self, model_alias, **selectors):
            captured["model_alias"] = model_alias
            captured["selectors"] = selectors
            return "SELECT 1 AS answer"

    class ExecutorStub:
        def __init__(self, database, read_only, file_search_path):
            captured["database"] = database
            captured["read_only"] = read_only
            captured["file_search_path"] = file_search_path

        def execute(self, sql_query):
            captured["sql_query"] = sql_query
            return pd.DataFrame({"answer": [1]})

    monkeypatch.setattr(dbt_module, "DBTManifestConnector", ManifestStub)
    monkeypatch.setattr(dbt_module, "DuckDBSQLExecutor", ExecutorStub)

    connector = dbt_module.DBTDuckDBConnector(
        model_alias="metrics_model",
        model_unique_id="model.pkg.metrics_model",
        model_package_name="pkg",
        model_selector_name="metrics_model",
        package_url="https://github.com/org/repo.git",
        project_dir="/tmp/workspace",
        database="/tmp/warehouse.duckdb",
        read_only=False,
        file_search_path=["/tmp/workspace"],
    )

    result = connector.fetch_data()

    assert result.to_dict(orient="records") == [{"answer": 1}]
    assert captured["model_alias"] == "metrics_model"
    assert captured["selectors"] == {
        "model_unique_id": "model.pkg.metrics_model",
        "model_package_name": "pkg",
        "model_selector_name": "metrics_model",
    }
    assert captured["database"] == "/tmp/warehouse.duckdb"
    assert captured["read_only"] is False
    assert captured["file_search_path"] == ["/tmp/workspace"]
    assert captured["sql_query"] == "SELECT 1 AS answer"
