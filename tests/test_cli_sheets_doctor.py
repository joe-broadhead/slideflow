import json

import pytest

import slideflow.cli.commands.sheets as sheets_command_module
from tests.cli_test_helpers import stub_sheets_cli_output


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


def test_sheets_doctor_writes_success_json(tmp_path, monkeypatch):
    stub_sheets_cli_output(monkeypatch)

    class _Provider:
        @staticmethod
        def run_preflight_checks():
            return [
                ("google_sheets_credentials_present", True, "Credentials present"),
                ("drive_folder_access", True, "Folder accessible"),
            ]

    monkeypatch.setattr(
        sheets_command_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: _Provider()),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-doctor.json"
    _write_minimal_workbook_config(config_file)

    payload = sheets_command_module.sheets_doctor_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
        strict=False,
    )

    assert payload["status"] == "success"
    json_payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert json_payload["command"] == "sheets doctor"
    assert json_payload["summary"]["failed_errors"] == 0


def test_sheets_doctor_strict_exits_on_error_check(tmp_path, monkeypatch):
    stub_sheets_cli_output(monkeypatch)

    class _Provider:
        @staticmethod
        def run_preflight_checks():
            return [("google_sheets_credentials_present", False, "Missing credentials")]

    monkeypatch.setattr(
        sheets_command_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: _Provider()),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-doctor-error.json"
    _write_minimal_workbook_config(config_file)

    with pytest.raises(sheets_command_module.typer.Exit) as exc_info:
        sheets_command_module.sheets_doctor_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            strict=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["summary"]["failed_errors"] == 1


def test_sheets_doctor_writes_error_json_on_provider_exception(tmp_path, monkeypatch):
    stub_sheets_cli_output(monkeypatch)
    monkeypatch.setattr(
        sheets_command_module.WorkbookProviderFactory,
        "create_provider",
        staticmethod(
            lambda _provider_config: (_ for _ in ()).throw(RuntimeError("boom"))
        ),
    )

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-doctor-unexpected-error.json"
    _write_minimal_workbook_config(config_file)

    with pytest.raises(sheets_command_module.typer.Exit):
        sheets_command_module.sheets_doctor_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            strict=False,
        )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_SHEETS_DOCTOR_FAILED"
