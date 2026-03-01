"""CLI commands for sheet-oriented workbook workflows."""

from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

import typer
import yaml  # type: ignore[import-untyped]

from slideflow.cli.commands._registry import resolve_registry_paths
from slideflow.cli.error_codes import CliErrorCode, resolve_cli_error_code
from slideflow.cli.json_output import now_iso8601_utc, write_output_json
from slideflow.cli.theme import print_error, print_success, print_validation_header
from slideflow.utilities import ConfigLoader
from slideflow.utilities.error_messages import safe_error_line
from slideflow.workbooks import WorkbookConfig

sheets_app = typer.Typer(help="Validate and build workbook outputs")


def _first_error_line(error: Exception) -> str:
    """Return a safe single-line error description."""
    return safe_error_line(error)


def _workbook_summary_payload(workbook_config: WorkbookConfig) -> Dict[str, Any]:
    """Build a compact workbook summary for machine-readable output."""
    tabs = workbook_config.workbook.tabs
    summaries = workbook_config.workbook.summaries
    append_tabs = sum(1 for tab in tabs if tab.mode == "append")
    replace_tabs = sum(1 for tab in tabs if tab.mode == "replace")
    return {
        "provider_type": workbook_config.provider.type,
        "workbook_title": workbook_config.workbook.title,
        "tabs": len(tabs),
        "append_tabs": append_tabs,
        "replace_tabs": replace_tabs,
        "summaries": len(summaries),
    }


def sheets_validate_command(
    config_file: Annotated[
        Path, typer.Argument(help="Path to workbook YAML configuration file")
    ],
    registry_paths: Annotated[
        Optional[List[Path]],
        typer.Option(
            "--registry",
            "-r",
            help="Path to Python registry files (can be used multiple times)",
        ),
    ] = None,
    output_json: Annotated[
        Optional[Path],
        typer.Option(
            "--output-json",
            help=(
                "Optional path to write a machine-readable workbook validation "
                "summary JSON file"
            ),
        ),
    ] = None,
) -> Dict[str, Any]:
    """Validate workbook YAML configuration."""
    print_validation_header(str(config_file))
    run_started_at = now_iso8601_utc()

    try:
        raw_config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        config_registry = (
            raw_config.get("registry") if isinstance(raw_config, dict) else None
        )

        resolved_registry_paths = resolve_registry_paths(
            config_file=config_file,
            cli_registry_paths=registry_paths,
            config_registry=config_registry,
        )

        loader = ConfigLoader(
            yaml_path=config_file,
            registry_paths=resolved_registry_paths,
        )
        workbook_config = WorkbookConfig.model_validate(loader.config)
        summary = _workbook_summary_payload(workbook_config)

        print_success()
        typer.echo(
            "✅ Workbook config is valid "
            f"({summary['tabs']} tab(s), {summary['summaries']} summary rule(s))."
        )

        result = {
            "command": "sheets validate",
            "status": "success",
            "started_at": run_started_at,
            "completed_at": now_iso8601_utc(),
            "config_file": str(config_file),
            "registry_files": [str(path) for path in resolved_registry_paths],
            "summary": summary,
        }
        write_output_json(output_json, result)
        return result

    except Exception as error:
        error_code = resolve_cli_error_code(error, CliErrorCode.SHEETS_VALIDATE_FAILED)
        result = {
            "command": "sheets validate",
            "status": "error",
            "started_at": run_started_at,
            "completed_at": now_iso8601_utc(),
            "config_file": str(config_file),
            "error": {"code": error_code, "message": _first_error_line(error)},
        }
        write_output_json(output_json, result)
        print_error(str(error), error_code=error_code)
        raise typer.Exit(1)


@sheets_app.command("validate")
def sheets_validate(
    config_file: Annotated[
        Path, typer.Argument(help="Path to workbook YAML configuration file")
    ],
    registry_paths: Annotated[
        Optional[List[Path]],
        typer.Option(
            "--registry",
            "-r",
            help="Path to Python registry files (can be used multiple times)",
        ),
    ] = None,
    output_json: Annotated[
        Optional[Path],
        typer.Option(
            "--output-json",
            help=(
                "Optional path to write a machine-readable workbook validation "
                "summary JSON file"
            ),
        ),
    ] = None,
) -> None:
    """Validate workbook YAML configuration without writing outputs."""
    sheets_validate_command(
        config_file=config_file,
        registry_paths=registry_paths,
        output_json=output_json,
    )
