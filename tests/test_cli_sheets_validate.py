import json
from pathlib import Path

import pytest

import slideflow.cli.commands.sheets as sheets_command_module


def _stub_cli_output(monkeypatch):
    monkeypatch.setattr(
        sheets_command_module, "print_validation_header", lambda *a, **k: None
    )
    monkeypatch.setattr(sheets_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module, "print_error", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module.typer, "echo", lambda *a, **k: None)


def _write_minimal_workbook_config(
    config_path: Path, registry: str | None = None
) -> None:
    registry_block = ""
    if registry is not None:
        registry_block = f"registry: {registry}\n"

    config_path.write_text(
        registry_block
        + "provider:\n"
        + "  type: google_sheets\n"
        + "  config: {}\n"
        + "workbook:\n"
        + "  title: Weekly KPI Snapshot\n"
        + "  tabs:\n"
        + "    - name: kpi_current\n"
        + "      mode: replace\n"
        + "      data_source:\n"
        + "        type: csv\n"
        + "        name: kpi_source\n"
        + "        file_path: kpi.csv\n",
        encoding="utf-8",
    )


def test_sheets_validate_writes_success_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-validate.json"
    _write_minimal_workbook_config(config_file)

    result = sheets_command_module.sheets_validate_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
    )

    assert result["status"] == "success"
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["command"] == "sheets validate"
    assert payload["summary"]["provider_type"] == "google_sheets"
    assert payload["summary"]["tabs"] == 1


def test_sheets_validate_uses_registry_from_config(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    registry_file = tmp_path / "custom_registry.py"
    registry_file.write_text("function_registry = {}\n", encoding="utf-8")

    config_file = tmp_path / "workbook.yaml"
    output_file = tmp_path / "sheets-validate-registry.json"
    _write_minimal_workbook_config(config_file, registry="custom_registry.py")

    result = sheets_command_module.sheets_validate_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
    )

    assert result["status"] == "success"
    assert result["registry_files"] == [str(registry_file.resolve())]


def test_sheets_validate_writes_error_json_on_invalid_config(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "workbook-invalid.yaml"
    output_file = tmp_path / "sheets-validate-error.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_sheets\n"
        "  config: {}\n"
        "workbook:\n"
        "  title: Weekly KPI Snapshot\n"
        "  tabs:\n"
        "    - name: kpi_current\n"
        "      mode: append\n"
        "      data_source:\n"
        "        type: csv\n"
        "        name: kpi_source\n"
        "        file_path: kpi.csv\n",
        encoding="utf-8",
    )

    with pytest.raises(sheets_command_module.typer.Exit) as exc_info:
        sheets_command_module.sheets_validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_SHEETS_VALIDATE_FAILED"
