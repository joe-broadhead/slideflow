from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pydantic import TypeAdapter, ValidationError

import slideflow.data.connectors.connect as connect_module
import slideflow.data.connectors.csv as csv_module
import slideflow.data.connectors.json as json_module
from slideflow.constants import Defaults


def test_csv_connector_fetch_data_reads_rows_and_logs(tmp_path: Path, monkeypatch):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")

    log_calls = []
    monkeypatch.setattr(
        csv_module,
        "log_data_operation",
        lambda *args, **kwargs: log_calls.append((args, kwargs)),
    )

    connector = csv_module.CSVConnector(str(csv_path))
    df = connector.fetch_data()

    assert len(df) == 2
    assert df.to_dict(orient="records")[0]["name"] == "alpha"
    assert log_calls == [
        (("fetch", "csv", 2), {"file_path": str(csv_path)}),
    ]


def test_csv_source_config_fetch_data_uses_connector(tmp_path: Path):
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("city,metric\nparis,10\n", encoding="utf-8")

    source = csv_module.CSVSourceConfig(
        name="cities",
        type="csv",
        file_path=csv_path,
    )
    df = source.fetch_data()

    assert len(df) == 1
    assert df.to_dict(orient="records")[0]["city"] == "paris"


def test_json_connector_fetch_data_uses_orient_and_logs(tmp_path: Path, monkeypatch):
    json_path = tmp_path / "records.json"
    json_path.write_text('[{"k":"a","v":1},{"k":"b","v":2}]', encoding="utf-8")

    read_calls = []
    log_calls = []

    def _fake_read_json(path, orient):
        read_calls.append((path, orient))
        return pd.DataFrame({"k": ["a", "b"], "v": [1, 2]})

    monkeypatch.setattr(json_module.pd, "read_json", _fake_read_json)
    monkeypatch.setattr(
        json_module,
        "log_data_operation",
        lambda *args, **kwargs: log_calls.append((args, kwargs)),
    )

    connector = json_module.JSONConnector(str(json_path), orient="records")
    df = connector.fetch_data()

    assert len(df) == 2
    assert read_calls == [(str(json_path), "records")]
    assert log_calls == [
        (
            ("fetch", "json", 2),
            {"file_path": str(json_path), "orient": "records"},
        )
    ]


def test_json_source_config_defaults_orient_from_constants(tmp_path: Path):
    json_path = tmp_path / "default.json"
    json_path.write_text('[{"id":1}]', encoding="utf-8")

    source = json_module.JSONSourceConfig(
        name="default_json",
        type="json",
        file_path=json_path,
    )

    assert source.orient == Defaults.JSON_ORIENT


def test_data_source_config_discriminator_supports_csv_and_json(tmp_path: Path):
    csv_path = tmp_path / "union.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    json_path = tmp_path / "union.json"
    json_path.write_text('[{"x":1}]', encoding="utf-8")

    adapter = TypeAdapter(connect_module.DataSourceConfig)
    csv_cfg = adapter.validate_python(
        {
            "type": "csv",
            "name": "csv_source",
            "file_path": str(csv_path),
        }
    )
    json_cfg = adapter.validate_python(
        {
            "type": "json",
            "name": "json_source",
            "file_path": str(json_path),
            "orient": "records",
        }
    )

    assert isinstance(csv_cfg, csv_module.CSVSourceConfig)
    assert isinstance(json_cfg, json_module.JSONSourceConfig)


def test_data_source_config_rejects_unknown_type():
    adapter = TypeAdapter(connect_module.DataSourceConfig)

    with pytest.raises(ValidationError, match="union_tag_invalid"):
        adapter.validate_python(
            {
                "type": "missing_type",
                "name": "bad",
            }
        )
