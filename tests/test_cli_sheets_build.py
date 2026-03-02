import json

import pytest

import slideflow.cli.commands.sheets as sheets_command_module
from slideflow.workbooks.base import (
    WorkbookBuildResult,
    WorkbookSummaryResult,
    WorkbookTabResult,
)


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


def _write_two_tab_workbook_config(config_file):
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
        "        file_path: kpi.csv\n"
        "    - name: kpi_previous\n"
        "      mode: replace\n"
        "      data_source:\n"
        "        type: csv\n"
        "        name: kpi_source_prev\n"
        "        file_path: kpi_prev.csv\n",
        encoding="utf-8",
    )


def test_sheets_build_writes_success_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    class _Builder:
        def build(self, **_kwargs):
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
                summary_results=[
                    WorkbookSummaryResult(
                        name="kpi_summary",
                        source_tab="kpi_current",
                        placement_type="same_sheet",
                        target_tab="kpi_current",
                        target_cell="H2",
                        status="success",
                        chars_written=42,
                    )
                ],
            )

    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_config",
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
    assert payload["runtime"]["threads"]["requested"] is None
    assert payload["runtime"]["threads"]["applied"] == 1
    assert payload["runtime"]["threads"]["supported_values"] == [1]
    assert payload["runtime"]["threads"]["effective_workers"] == 1
    assert payload["runtime"]["threads"]["workload_size"] == 1
    assert payload["runtime"]["requests_per_second"]["requested"] is None
    assert payload["runtime"]["requests_per_second"]["applied"] == 1.0
    assert payload["runtime"]["requests_per_second"]["source"] == "provider_config"
    json_payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert json_payload["command"] == "sheets build"
    assert json_payload["summary"]["workbook_id"] == "sheet_123"
    assert json_payload["summary"]["tabs_succeeded"] == 1
    assert json_payload["summary"]["summaries_succeeded"] == 1
    assert json_payload["summaries"][0]["name"] == "kpi_summary"


def test_sheets_build_writes_error_json_and_exits_on_tab_failures(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    class _Builder:
        def build(self, **_kwargs):
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
        "from_config",
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
    assert "tab errors" in payload["error"]["message"]


def test_sheets_build_writes_error_json_and_exits_on_summary_failures(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    class _Builder:
        def build(self, **_kwargs):
            return WorkbookBuildResult(
                workbook_id="sheet_123",
                workbook_url="https://docs.google.com/spreadsheets/d/sheet_123",
                status="error",
                tab_results=[
                    WorkbookTabResult(
                        tab_name="kpi_current",
                        mode="replace",
                        status="success",
                        rows_written=2,
                    )
                ],
                summary_results=[
                    WorkbookSummaryResult(
                        name="kpi_summary",
                        source_tab="kpi_current",
                        placement_type="same_sheet",
                        target_tab="kpi_current",
                        target_cell="H2",
                        status="error",
                        error="missing api key",
                    )
                ],
            )

    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_config",
        staticmethod(lambda *args, **kwargs: _Builder()),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-build-summary-error.json"
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
    assert payload["summary"]["summaries_failed"] == 1
    assert "summary errors" in payload["error"]["message"]


def test_sheets_build_writes_error_json_on_unexpected_failure(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_config",
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


def test_sheets_build_runtime_overrides_are_reflected_in_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    captured = {}

    class _Builder:
        def build(self, threads=1):
            captured["builder_threads"] = threads
            return WorkbookBuildResult(
                workbook_id="sheet_123",
                workbook_url="https://docs.google.com/spreadsheets/d/sheet_123",
                status="success",
                tab_results=[],
                summary_results=[],
            )

    def _from_config(config):
        captured["requests_per_second"] = config.provider.config.get(
            "requests_per_second"
        )
        return _Builder()

    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_config",
        staticmethod(_from_config),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-build-runtime.json"
    _write_minimal_workbook_config(config_file)

    payload = sheets_command_module.sheets_build_command(
        config_file=config_file,
        registry_paths=None,
        threads=1,
        requests_per_second=2.5,
        output_json=output_file,
    )

    assert captured["requests_per_second"] == 2.5
    assert captured["builder_threads"] == 1
    assert payload["runtime"]["threads"] == {
        "requested": 1,
        "applied": 1,
        "supported_values": [1],
        "effective_workers": 1,
        "workload_size": 1,
    }
    assert payload["runtime"]["requests_per_second"] == {
        "requested": 2.5,
        "applied": 2.5,
        "source": "cli_override",
    }

    json_payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert json_payload["runtime"] == payload["runtime"]


def test_sheets_build_applies_thread_cap_from_workload_and_emits_warning(
    tmp_path, monkeypatch
):
    warning_messages = []
    monkeypatch.setattr(
        sheets_command_module, "print_validation_header", lambda *a, **k: None
    )
    monkeypatch.setattr(sheets_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module, "print_error", lambda *a, **k: None)
    monkeypatch.setattr(
        sheets_command_module.typer,
        "echo",
        lambda message, *a, **k: warning_messages.append(str(message)),
    )

    class _Builder:
        def build(self, threads=1):
            warning_messages.append(f"builder_threads={threads}")
            return WorkbookBuildResult(
                workbook_id="sheet_123",
                workbook_url="https://docs.google.com/spreadsheets/d/sheet_123",
                status="success",
                tab_results=[],
                summary_results=[],
            )

    monkeypatch.setattr(
        sheets_command_module.WorkbookBuilder,
        "from_config",
        staticmethod(lambda *args, **kwargs: _Builder()),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-build-threads.json"
    _write_two_tab_workbook_config(config_file)

    payload = sheets_command_module.sheets_build_command(
        config_file=config_file,
        registry_paths=None,
        threads=4,
        output_json=output_file,
    )

    assert payload["runtime"]["threads"] == {
        "requested": 4,
        "applied": 2,
        "supported_values": [1, 2],
        "effective_workers": 2,
        "workload_size": 2,
    }
    assert any("applying 2 worker(s)" in msg for msg in warning_messages)
    assert "builder_threads=2" in warning_messages
