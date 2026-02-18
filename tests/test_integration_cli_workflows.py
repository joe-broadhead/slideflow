from pathlib import Path

import pytest

import slideflow.cli.commands.build as build_command_module
import slideflow.cli.commands.validate as validate_command_module


def _stub_cli_output(monkeypatch):
    monkeypatch.setattr(build_command_module, "print_build_header", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module, "print_build_progress", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module, "print_build_success", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module, "print_build_error", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module.time, "sleep", lambda *_: None)

    monkeypatch.setattr(validate_command_module, "print_validation_header", lambda *a, **k: None)
    monkeypatch.setattr(validate_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(validate_command_module, "print_config_summary", lambda *a, **k: None)
    monkeypatch.setattr(validate_command_module, "print_error", lambda *a, **k: None)


def _write_registry(registry_path: Path) -> None:
    registry_path.write_text(
        "def build_region_label(region='unknown'):\n"
        "    return f'Region: {region}'\n"
        "\n"
        "function_registry = {\n"
        "    'build_region_label': build_region_label,\n"
        "}\n",
        encoding="utf-8",
    )


def _write_config(config_path: Path) -> None:
    config_path.write_text(
        "registry: registry.py\n"
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: 'Regional Deck {region}'\n"
        "  slides:\n"
        "    - id: slide_1\n"
        "      title: Overview\n"
        "      replacements:\n"
        "        - type: text\n"
        "          config:\n"
        "            placeholder: '{{REGION_LABEL}}'\n"
        "            value_fn: build_region_label\n"
        "            value_fn_args:\n"
        "              region: '{region}'\n"
        "      charts: []\n",
        encoding="utf-8",
    )


@pytest.mark.integration
def test_validate_command_with_real_loader_and_registry(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    monkeypatch.chdir(tmp_path)

    registry_path = tmp_path / "registry.py"
    config_path = tmp_path / "config.yml"
    _write_registry(registry_path)
    _write_config(config_path)

    validate_command_module.validate_command(config_file=config_path, registry_paths=None)


@pytest.mark.integration
def test_validate_fails_when_registry_function_is_missing(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    monkeypatch.chdir(tmp_path)

    config_path = tmp_path / "broken.yml"
    config_path.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: 'Broken Deck'\n"
        "  slides:\n"
        "    - id: slide_1\n"
        "      replacements:\n"
        "        - type: text\n"
        "          config:\n"
        "            placeholder: '{{X}}'\n"
        "            value_fn: missing_function\n"
        "      charts: []\n",
        encoding="utf-8",
    )

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(config_file=config_path, registry_paths=None)

    assert exc_info.value.code == 1


@pytest.mark.e2e
def test_e2e_validate_then_build_dry_run_with_param_csv(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    monkeypatch.chdir(tmp_path)

    registry_path = tmp_path / "registry.py"
    config_path = tmp_path / "config.yml"
    params_path = tmp_path / "params.csv"

    _write_registry(registry_path)
    _write_config(config_path)
    params_path.write_text(
        "region\nus\neu\n",
        encoding="utf-8",
    )

    validate_command_module.validate_command(config_file=config_path, registry_paths=None)

    result = build_command_module.build_command(
        config_file=config_path,
        registry_files=None,
        params_path=params_path,
        dry_run=True,
    )
    assert result == []
