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


def test_sheets_validate_counts_tab_local_ai_summaries(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "workbook-with-summaries.yaml"
    output_file = tmp_path / "sheets-validate-with-summaries.json"
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
        "      ai:\n"
        "        summaries:\n"
        "          - type: ai_text\n"
        "            config:\n"
        "              name: kpi_summary\n"
        "              provider: openai\n"
        "              provider_args: {}\n"
        "              prompt: Summarize\n"
        "              placement:\n"
        "                type: same_sheet\n"
        "                anchor_cell: H2\n",
        encoding="utf-8",
    )

    result = sheets_command_module.sheets_validate_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
    )

    assert result["status"] == "success"
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["summary"]["summaries"] == 1


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


def test_sheets_validate_writes_error_json_on_removed_workbook_summaries(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "workbook-legacy.yaml"
    output_file = tmp_path / "sheets-validate-legacy-error.json"
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
        "  summaries: []\n",
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
    assert "workbook.summaries is removed" in payload["error"]["message"]


def test_sheets_validate_rejects_summary_tab_without_target_tab(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "workbook-missing-summary-target.yaml"
    output_file = tmp_path / "sheets-validate-missing-summary-target.json"
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
        "      ai:\n"
        "        summaries:\n"
        "          - type: ai_text\n"
        "            config:\n"
        "              name: kpi_summary\n"
        "              provider: openai\n"
        "              provider_args: {}\n"
        "              prompt: Summarize\n"
        "              placement:\n"
        "                type: summary_tab\n",
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
    assert "target_tab is required when placement.type='summary_tab'" in payload[
        "error"
    ]["message"]


def test_sheets_validate_rejects_summary_tab_target_matching_source(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "workbook-summary-tab-same-target.yaml"
    output_file = tmp_path / "sheets-validate-summary-tab-same-target.json"
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
        "      ai:\n"
        "        summaries:\n"
        "          - type: ai_text\n"
        "            config:\n"
        "              name: kpi_summary\n"
        "              provider: openai\n"
        "              provider_args: {}\n"
        "              prompt: Summarize\n"
        "              placement:\n"
        "                type: summary_tab\n"
        "                target_tab: kpi_current\n",
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
    assert "must differ from the source tab when placement.type='summary_tab'" in payload[
        "error"
    ]["message"]
