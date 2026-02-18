from pathlib import Path
import tomllib

import pytest
from pydantic import TypeAdapter

import slideflow
from slideflow.cli.commands import build_command, validate_command
from slideflow.data.connectors import (
    CSVSourceConfig,
    DBTDatabricksSourceConfig,
    DatabricksSourceConfig,
    DataSourceConfig,
    JSONSourceConfig,
)
from slideflow.presentations.charts import (
    ChartUnion,
    CustomChart,
    PlotlyGraphObjects,
    TemplateChart,
)
from slideflow.replacements import (
    AITextReplacement,
    ReplacementUnion,
    TableReplacement,
    TextReplacement,
)


def test_public_identity_contracts_remain_stable():
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]

    assert project["name"] == "slideflow-presentations"
    assert project["scripts"]["slideflow"] == "slideflow.cli.main:app"
    assert slideflow.__name__ == "slideflow"


def test_cli_commands_remain_available():
    assert callable(build_command)
    assert callable(validate_command)


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {"type": "csv", "name": "source_csv", "file_path": "data.csv"},
            CSVSourceConfig,
        ),
        (
            {"type": "json", "name": "source_json", "file_path": "data.json"},
            JSONSourceConfig,
        ),
        (
            {
                "type": "databricks",
                "name": "source_databricks",
                "query": "SELECT 1",
            },
            DatabricksSourceConfig,
        ),
        (
            {
                "type": "databricks_dbt",
                "name": "source_dbt",
                "model_alias": "model_a",
                "package_url": "https://github.com/example/dbt-project.git",
                "project_dir": "/tmp/dbt_project",
            },
            DBTDatabricksSourceConfig,
        ),
    ],
)
def test_data_connector_matrix_remains_supported(payload, expected_type):
    adapter = TypeAdapter(DataSourceConfig)
    parsed = adapter.validate_python(payload)

    assert isinstance(parsed, expected_type)


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "type": "text",
                "placeholder": "{{TITLE}}",
                "replacement": "Quarterly Review",
            },
            TextReplacement,
        ),
        (
            {
                "type": "table",
                "prefix": "TABLE_",
                "replacements": {"{{TABLE_1,1}}": "Value"},
            },
            TableReplacement,
        ),
        (
            {
                "type": "ai_text",
                "placeholder": "{{SUMMARY}}",
                "prompt": "Summarize this report.",
            },
            AITextReplacement,
        ),
    ],
)
def test_replacement_matrix_remains_supported(payload, expected_type):
    adapter = TypeAdapter(ReplacementUnion)
    parsed = adapter.validate_python(payload)

    assert isinstance(parsed, expected_type)


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        (
            {
                "type": "plotly_go",
                "traces": [{"type": "bar", "x": [1, 2], "y": [3, 4]}],
            },
            PlotlyGraphObjects,
        ),
        (
            {
                "type": "custom",
                "chart_fn": lambda *_args, **_kwargs: b"png-bytes",
                "chart_config": {},
            },
            CustomChart,
        ),
        (
            {
                "type": "template",
                "template_name": "example_template",
                "template_config": {},
            },
            TemplateChart,
        ),
    ],
)
def test_chart_matrix_remains_supported(payload, expected_type):
    adapter = TypeAdapter(ChartUnion)
    parsed = adapter.validate_python(payload)

    assert isinstance(parsed, expected_type)
