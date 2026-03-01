"""CLI commands for sheet-oriented workbook workflows."""

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

import typer
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError as PydanticValidationError

from slideflow.cli.commands._registry import resolve_registry_paths
from slideflow.cli.error_codes import CliErrorCode, resolve_cli_error_code
from slideflow.cli.json_output import now_iso8601_utc, write_output_json
from slideflow.cli.theme import print_error, print_success, print_validation_header
from slideflow.utilities import ConfigLoader
from slideflow.utilities.error_messages import safe_error_line
from slideflow.workbooks import WorkbookBuilder, WorkbookConfig
from slideflow.workbooks.providers.factory import WorkbookProviderFactory

sheets_app = typer.Typer(help="Validate and build workbook outputs")
CheckSeverity = Literal["error", "warning", "info"]


def _first_error_line(error: Exception) -> str:
    """Return a safe single-line error description."""
    if isinstance(error, PydanticValidationError):
        details = error.errors()
        if details:
            msg = str(details[0].get("msg", "")).strip()
            if msg:
                return msg
    return safe_error_line(error)


def _check(
    name: str, ok: bool, detail: str, severity: CheckSeverity = "error"
) -> Dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "severity": severity}


def _load_workbook_config(
    config_file: Path,
    registry_paths: Optional[List[Path]],
) -> tuple[WorkbookConfig, List[Path]]:
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
    return workbook_config, resolved_registry_paths


def _workbook_summary_payload(workbook_config: WorkbookConfig) -> Dict[str, Any]:
    """Build a compact workbook summary for machine-readable output."""
    tabs = workbook_config.workbook.tabs
    summaries = workbook_config.workbook.iter_summary_specs()
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
        workbook_config, resolved_registry_paths = _load_workbook_config(
            config_file=config_file,
            registry_paths=registry_paths,
        )
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


def sheets_build_command(
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
            help="Optional path to write a machine-readable workbook build summary JSON file",
        ),
    ] = None,
) -> Dict[str, Any]:
    """Build workbook outputs from a workbook configuration."""
    print_validation_header(str(config_file))
    run_started_at = now_iso8601_utc()

    try:
        _, resolved_registry_paths = _load_workbook_config(
            config_file=config_file,
            registry_paths=registry_paths,
        )

        builder = WorkbookBuilder.from_yaml(
            yaml_path=config_file,
            registry_paths=resolved_registry_paths,
        )
        result = builder.build()
        summary = {
            "workbook_id": result.workbook_id,
            "workbook_url": result.workbook_url,
            "tabs_total": result.tabs_total,
            "tabs_succeeded": result.tabs_succeeded,
            "tabs_failed": result.tabs_failed,
            "idempotent_skips": result.idempotent_skips,
            "summaries_total": result.summaries_total,
            "summaries_succeeded": result.summaries_succeeded,
            "summaries_failed": result.summaries_failed,
        }
        payload = {
            "command": "sheets build",
            "status": result.status,
            "started_at": run_started_at,
            "completed_at": now_iso8601_utc(),
            "config_file": str(config_file),
            "registry_files": [str(path) for path in resolved_registry_paths],
            "summary": summary,
            "tabs": [tab.model_dump() for tab in result.tab_results],
            "summaries": [
                summary_result.model_dump() for summary_result in result.summary_results
            ],
        }

        if result.status == "error":
            failure_messages: List[str] = []
            if result.tabs_failed:
                failure_messages.append(
                    f"tab errors ({result.tabs_failed}/{result.tabs_total} failed)"
                )
            if result.summaries_failed:
                failure_messages.append(
                    "summary errors "
                    f"({result.summaries_failed}/{result.summaries_total} failed)"
                )
            failure_suffix = " and ".join(failure_messages) or "unknown errors"
            error_message = f"Workbook build completed with {failure_suffix}."
            payload["error"] = {
                "code": CliErrorCode.SHEETS_BUILD_FAILED,
                "message": error_message,
            }
            write_output_json(output_json, payload)
            print_error(
                error_message,
                error_code=CliErrorCode.SHEETS_BUILD_FAILED,
            )
            raise typer.Exit(1)

        write_output_json(output_json, payload)
        print_success()
        typer.echo(
            "✅ Workbook build complete " f"({result.tabs_succeeded} tab(s) succeeded)."
        )
        typer.echo(f"Workbook URL: {result.workbook_url}")
        return payload
    except typer.Exit:
        raise
    except Exception as error:
        error_code = resolve_cli_error_code(error, CliErrorCode.SHEETS_BUILD_FAILED)
        payload = {
            "command": "sheets build",
            "status": "error",
            "started_at": run_started_at,
            "completed_at": now_iso8601_utc(),
            "config_file": str(config_file),
            "error": {"code": error_code, "message": _first_error_line(error)},
        }
        write_output_json(output_json, payload)
        print_error(str(error), error_code=error_code)
        raise typer.Exit(1)


def sheets_doctor_command(
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
            help="Optional path to write a machine-readable sheets doctor summary JSON file",
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit non-zero when any error-severity checks fail",
        ),
    ] = False,
) -> Dict[str, Any]:
    """Run preflight diagnostics for workbook provider configuration/runtime."""
    print_validation_header(str(config_file))
    started_at = now_iso8601_utc()
    checks: List[Dict[str, Any]] = []

    try:
        workbook_config, resolved_registry_paths = _load_workbook_config(
            config_file=config_file,
            registry_paths=registry_paths,
        )
        checks.append(
            _check(
                "config_validation",
                True,
                "Workbook configuration validated successfully",
                "error",
            )
        )

        provider = WorkbookProviderFactory.create_provider(workbook_config.provider)
        checks.append(
            _check(
                "provider_init",
                True,
                f"Initialized workbook provider '{workbook_config.provider.type}'",
                "error",
            )
        )
        for check_name, ok, detail in provider.run_preflight_checks():
            checks.append(_check(f"provider:{check_name}", ok, detail, "error"))

        error_failures = [
            check
            for check in checks
            if not check["ok"] and check["severity"] == "error"
        ]
        warning_failures = [
            check
            for check in checks
            if not check["ok"] and check["severity"] == "warning"
        ]

        status = "success"
        if error_failures:
            status = "error"
        elif warning_failures:
            status = "warning"

        payload = {
            "command": "sheets doctor",
            "status": status,
            "strict": strict,
            "started_at": started_at,
            "completed_at": now_iso8601_utc(),
            "config_file": str(config_file),
            "registry_files": [str(path) for path in resolved_registry_paths],
            "checks": checks,
            "summary": {
                "total": len(checks),
                "passed": sum(1 for check in checks if check["ok"]),
                "failed_errors": len(error_failures),
                "failed_warnings": len(warning_failures),
            },
        }
        write_output_json(output_json, payload)

        for check in checks:
            icon = "✅" if check["ok"] else "❌"
            severity = check["severity"].upper()
            typer.echo(f"{icon} [{severity}] {check['name']}: {check['detail']}")

        if strict and error_failures:
            raise typer.Exit(1)

        return payload
    except typer.Exit:
        raise
    except Exception as error:
        error_code = resolve_cli_error_code(error, CliErrorCode.SHEETS_DOCTOR_FAILED)
        payload = {
            "command": "sheets doctor",
            "status": "error",
            "strict": strict,
            "started_at": started_at,
            "completed_at": now_iso8601_utc(),
            "config_file": str(config_file),
            "checks": checks,
            "error": {"code": error_code, "message": _first_error_line(error)},
        }
        write_output_json(output_json, payload)
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


@sheets_app.command("build")
def sheets_build(
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
            help="Optional path to write a machine-readable workbook build summary JSON file",
        ),
    ] = None,
) -> None:
    """Build workbook outputs from a workbook YAML configuration."""
    sheets_build_command(
        config_file=config_file,
        registry_paths=registry_paths,
        output_json=output_json,
    )


@sheets_app.command("doctor")
def sheets_doctor(
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
            help="Optional path to write a machine-readable sheets doctor summary JSON file",
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit non-zero when any error-severity checks fail",
        ),
    ] = False,
) -> None:
    """Run workbook provider preflight diagnostics."""
    sheets_doctor_command(
        config_file=config_file,
        registry_paths=registry_paths,
        output_json=output_json,
        strict=strict,
    )
