import importlib
from pathlib import Path
from types import SimpleNamespace

import slideflow.cli.main as cli_main_module
import slideflow.cli.theme as theme_module
import slideflow.cli.utils as cli_utils_module
import slideflow.utilities.logging as logging_module


def _sample_presentation_config():
    slide = SimpleNamespace(
        replacements=[
            SimpleNamespace(config={"data_source": {"type": "csv"}}),
            SimpleNamespace(config={}),
        ],
        charts=[
            SimpleNamespace(config={"data_source": {"type": "json"}}),
        ],
    )
    return SimpleNamespace(
        presentation=SimpleNamespace(name="Demo Deck", slides=[slide]),
        data_sources={"warehouse": SimpleNamespace(type="databricks")},
    )


def test_theme_output_helpers_emit_expected_messages(monkeypatch):
    calls = []
    monkeypatch.setattr(
        theme_module.console, "print", lambda *a, **k: calls.append((a, k))
    )

    theme_module.print_slideflow_banner()
    theme_module.print_validation_header("config.yml")
    theme_module.print_success()
    theme_module.print_config_summary(_sample_presentation_config())
    theme_module.print_error("line1\nline2")
    theme_module.print_build_header("config.yml")
    theme_module.print_build_progress(2, 4, "Processing")
    theme_module.print_build_success("https://slides.example/test")
    theme_module.print_build_error("boom\ndetails")
    theme_module.print_help_footer()

    rendered = [str(args[0]) for args, _ in calls if args]
    assert any("Validation Complete" in entry for entry in rendered)
    assert any("Validation Failed" in entry for entry in rendered)
    assert any("Build Complete" in entry for entry in rendered)
    assert any("line1" in entry for entry in rendered)
    assert all(
        "line2" not in entry
        for entry in rendered
        if "line1" in entry and "red" in entry
    )


def test_theme_build_error_verbose_includes_full_message(monkeypatch):
    calls = []
    monkeypatch.setattr(
        theme_module.console, "print", lambda *a, **k: calls.append((a, k))
    )

    theme_module.print_build_error("line1\nline2", verbose=True)
    rendered = [str(args[0]) for args, _ in calls if args]

    assert any("line1\nline2" in entry for entry in rendered)


def test_theme_validation_error_verbose_includes_full_message(monkeypatch):
    calls = []
    monkeypatch.setattr(
        theme_module.console, "print", lambda *a, **k: calls.append((a, k))
    )

    theme_module.print_error("line1\nline2", verbose=True)
    rendered = [str(args[0]) for args, _ in calls if args]

    assert any("line1\nline2" in entry for entry in rendered)


def test_cli_utils_helpers_emit_summary_and_error(monkeypatch):
    header_calls = []
    summary_calls = []
    error_calls = []

    monkeypatch.setattr(
        cli_utils_module.theme,
        "print_validation_header",
        lambda config_file: header_calls.append(config_file),
    )
    monkeypatch.setattr(
        cli_utils_module.theme,
        "print_config_summary",
        lambda config: summary_calls.append(config),
    )
    monkeypatch.setattr(
        cli_utils_module.theme,
        "print_error",
        lambda error_msg, verbose=False, error_code=None: error_calls.append(
            (error_msg, verbose, error_code)
        ),
    )

    config = _sample_presentation_config()
    cli_utils_module.print_validation_header(Path("config.yml"))
    cli_utils_module.print_config_summary(config)
    cli_utils_module.handle_validation_error(RuntimeError("simple error"))
    cli_utils_module.handle_validation_error(RuntimeError("line1\nline2"), verbose=True)

    assert header_calls == ["config.yml"]
    assert summary_calls == [config]
    assert len(error_calls) == 2
    assert str(error_calls[0][0]) == "simple error"
    assert error_calls[0][1] is False
    assert str(error_calls[1][0]) == "line1\nline2"
    assert error_calls[1][1] is True


def test_logging_module_import_does_not_auto_configure_basic_config(monkeypatch):
    basic_config_calls = []
    monkeypatch.setattr(
        logging_module.logging,
        "basicConfig",
        lambda *args, **kwargs: basic_config_calls.append((args, kwargs)),
    )

    importlib.reload(logging_module)

    assert basic_config_calls == []


def test_main_sets_log_level_and_prints_banner_only_without_subcommand(monkeypatch):
    setup_calls = []
    banner_calls = []
    footer_calls = []

    monkeypatch.setattr(
        cli_main_module,
        "setup_logging",
        lambda level, enable_debug: setup_calls.append((level, enable_debug)),
    )
    monkeypatch.setattr(
        cli_main_module, "print_slideflow_banner", lambda: banner_calls.append(True)
    )
    monkeypatch.setattr(
        cli_main_module, "print_help_footer", lambda: footer_calls.append(True)
    )

    ctx = SimpleNamespace(invoked_subcommand=None)
    cli_main_module.main(ctx, verbose=True, debug=False, quiet=False)
    assert setup_calls[-1] == ("INFO", False)
    assert banner_calls and footer_calls

    ctx.invoked_subcommand = "build"
    cli_main_module.main(ctx, verbose=False, debug=True, quiet=False)
    assert setup_calls[-1] == ("DEBUG", True)

    cli_main_module.main(ctx, verbose=True, debug=True, quiet=True)
    assert setup_calls[-1] == ("ERROR", True)
