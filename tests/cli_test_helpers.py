"""Shared CLI test helper utilities."""

import slideflow.cli.commands.build as build_command_module
import slideflow.cli.commands.sheets as sheets_command_module
import slideflow.cli.commands.validate as validate_command_module


def stub_build_validate_cli_output(monkeypatch) -> None:
    """Disable build/validate CLI rich output in tests."""
    monkeypatch.setattr(
        build_command_module, "print_build_header", lambda *a, **k: None
    )
    monkeypatch.setattr(
        build_command_module, "print_build_progress", lambda *a, **k: None
    )
    monkeypatch.setattr(
        build_command_module, "print_build_success", lambda *a, **k: None
    )
    monkeypatch.setattr(build_command_module, "print_build_error", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module.time, "sleep", lambda *_: None)

    monkeypatch.setattr(
        validate_command_module, "print_validation_header", lambda *a, **k: None
    )
    monkeypatch.setattr(validate_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(
        validate_command_module, "print_config_summary", lambda *a, **k: None
    )
    monkeypatch.setattr(validate_command_module, "print_error", lambda *a, **k: None)


def stub_sheets_cli_output(monkeypatch) -> None:
    """Disable sheets CLI rich output in tests."""
    monkeypatch.setattr(
        sheets_command_module, "print_validation_header", lambda *a, **k: None
    )
    monkeypatch.setattr(sheets_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module, "print_error", lambda *a, **k: None)
    monkeypatch.setattr(sheets_command_module.typer, "echo", lambda *a, **k: None)
