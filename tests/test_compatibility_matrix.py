import tomllib
from pathlib import Path

import pytest
from pydantic import TypeAdapter

import slideflow
from slideflow.cli.commands import (
    build_command,
    sheets_build_command,
    sheets_doctor_command,
    sheets_validate_command,
    validate_command,
)
from slideflow.data.connectors import (
    CSVSourceConfig,
    DatabricksSourceConfig,
    DataSourceConfig,
    DBTDatabricksSourceConfig,
    DBTSourceConfig,
    DuckDBSourceConfig,
    JSONSourceConfig,
    RedshiftSourceConfig,
)
from slideflow.presentations.builder import PresentationBuilder
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
from slideflow.workbooks.config import WorkbookTabSpec


def test_public_identity_contracts_remain_stable():
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]

    assert project["name"] == "slideflow-presentations"
    assert project["scripts"]["slideflow"] == "slideflow.cli.main:app"
    assert slideflow.__name__ == "slideflow"


def test_cli_commands_remain_available():
    assert callable(build_command)
    assert callable(validate_command)
    assert callable(sheets_build_command)
    assert callable(sheets_doctor_command)
    assert callable(sheets_validate_command)


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
                "type": "duckdb",
                "name": "source_duckdb",
                "query": "SELECT 1",
            },
            DuckDBSourceConfig,
        ),
        (
            {
                "type": "redshift",
                "name": "source_redshift",
                "query": "SELECT 1",
                "host": "redshift.example.com",
                "database": "analytics",
                "user": "report_user",
                "password": "secret",
            },
            RedshiftSourceConfig,
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
        (
            {
                "type": "dbt",
                "name": "source_dbt_composable",
                "model_alias": "model_a",
                "dbt": {
                    "package_url": "https://github.com/example/dbt-project.git",
                    "project_dir": "/tmp/dbt_project",
                },
                "warehouse": {"type": "databricks"},
            },
            DBTSourceConfig,
        ),
    ],
)
def test_data_connector_matrix_remains_supported(payload, expected_type):
    adapter = TypeAdapter(DataSourceConfig)
    parsed = adapter.validate_python(payload)

    assert isinstance(parsed, expected_type)


def test_dbt_identity_selectors_survive_slide_and_workbook_config_building():
    dbt_source = {
        "type": "dbt",
        "name": "source_dbt_composable",
        "model_alias": "monthly_revenue",
        "model_unique_id": "model.analytics.monthly_revenue",
        "model_package_name": "analytics",
        "model_selector_name": "monthly_revenue",
        "dbt": {
            "package_url": "https://github.com/example/dbt-project.git",
            "project_dir": "/tmp/dbt_project",
            "target": "dev",
        },
        "warehouse": {"type": "databricks"},
    }

    table = TypeAdapter(ReplacementUnion).validate_python(
        {"type": "table", "prefix": "TABLE_", "data_source": dbt_source}
    )
    chart_source = PresentationBuilder._build_data_source(dbt_source)
    chart = TypeAdapter(ChartUnion).validate_python(
        {
            "type": "plotly_go",
            "traces": [{"type": "bar", "x": [1], "y": [2]}],
            "data_source": chart_source,
        }
    )
    workbook_tab = WorkbookTabSpec.model_validate(
        {"name": "Metrics", "data_source": dbt_source}
    )

    for parsed in (table.data_source, chart.data_source, workbook_tab.data_source):
        assert isinstance(parsed, DBTSourceConfig)
        assert parsed.model_alias == "monthly_revenue"
        assert parsed.model_unique_id == "model.analytics.monthly_revenue"
        assert parsed.model_package_name == "analytics"
        assert parsed.model_selector_name == "monthly_revenue"


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
