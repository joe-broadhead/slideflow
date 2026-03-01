import json

import pytest

import slideflow.cli.commands.sheets as sheets_command_module
from slideflow.workbooks.base import WorkbookBuildResult, WorkbookTabResult


def _stub_cli_output(monkeypatch):
    monkeypatch.setattr(
        sheets_command_module, "print_validation_header", lambda *a, **k: None
    )
    monkeypatch.setattr(sheets_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module, "print_error", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module.typer, "echo", lambda *a, **k: None)


def _write_minimal_workbook_config(config_file):
    config_file.write_text(
        "provider:\n"
        "  type: google_sheets\n"
        "  config: {}\n"
        "workbook:\n"
        "  title: Weekly KPI Snapshot\n"
        "  tabs:\n"
        "    - name: kpi_current\n"
        "      mode: replace\n"
        "      data_source:\n"
        "        type: csv\n"
        "        name: kpi_source\n"
        "        file_path: kpi.csv\n",
        encoding="utf-8",
    )


def test_sheets_build_writes_success_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    class _Builder:
        def build(self):
            return WorkbookBuildResult(
                workbook_id="sheet_123",
                workbook_url="https://docs.google.com/spreadsheets/d/sheet_123",
                status="success",
                tab_results=[
                    WorkbookTabResult(
                        tab_name="kpi_current",
                        mode="replace",
                        status="success",
                        rows_written=3,
                    )
                ],
            )

    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_yaml",
        staticmethod(lambda *args, **kwargs: _Builder()),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-build.json"
    _write_minimal_workbook_config(config_file)

    payload = sheets_command_module.sheets_build_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
    )

    assert payload["status"] == "success"
    json_payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert json_payload["command"] == "sheets build"
    assert json_payload["summary"]["workbook_id"] == "sheet_123"
    assert json_payload["summary"]["tabs_succeeded"] == 1


def test_sheets_build_writes_error_json_and_exits_on_tab_failures(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    class _Builder:
        def build(self):
            return WorkbookBuildResult(
                workbook_id="sheet_123",
                workbook_url="https://docs.google.com/spreadsheets/d/sheet_123",
                status="error",
                tab_results=[
                    WorkbookTabResult(
                        tab_name="kpi_current",
                        mode="replace",
                        status="error",
                        error="boom",
                    )
                ],
            )

    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_yaml",
        staticmethod(lambda *args, **kwargs: _Builder()),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-build-error.json"
    _write_minimal_workbook_config(config_file)

    with pytest.raises(sheets_command_module.typer.Exit) as exc_info:
        sheets_command_module.sheets_build_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_SHEETS_BUILD_FAILED"


def test_sheets_build_writes_error_json_on_unexpected_failure(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_yaml",
        staticmethod(
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        ),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-build-unexpected-error.json"
    _write_minimal_workbook_config(config_file)

    with pytest.raises(sheets_command_module.typer.Exit):
        sheets_command_module.sheets_build_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
        )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_SHEETS_BUILD_FAILED"
