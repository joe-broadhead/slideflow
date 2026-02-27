"""Doctor command for local/runtime preflight diagnostics."""

import os
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

import typer
import yaml  # type: ignore[import-untyped]

from slideflow.cli.commands._registry import resolve_registry_paths
from slideflow.cli.error_codes import CliErrorCode, resolve_cli_error_code
from slideflow.cli.json_output import now_iso8601_utc, write_output_json
from slideflow.constants import Environment
from slideflow.presentations.config import PresentationConfig
from slideflow.presentations.providers.factory import ProviderFactory
from slideflow.utilities import ConfigLoader
from slideflow.utilities.error_messages import safe_error_line

CheckSeverity = Literal["error", "warning", "info"]


def _check(
    name: str, ok: bool, detail: str, severity: CheckSeverity = "error"
) -> Dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "severity": severity}


def _first_error_line(error: Exception) -> str:
    """Return a safe single-line error description."""
    return safe_error_line(error)


def _resolve_binary_candidate(candidate: Optional[str]) -> Optional[str]:
    """Resolve a browser candidate as an absolute path when possible."""
    if not candidate:
        return None

    candidate = candidate.strip()
    if not candidate:
        return None

    candidate_path = Path(candidate)
    if candidate_path.exists():
        return str(candidate_path)

    resolved = shutil.which(candidate)
    if resolved and Path(resolved).exists():
        return resolved

    return None


def _detect_chrome_binary() -> Optional[str]:
    candidates = [
        os.getenv("CHROME_PATH"),
        os.getenv("GOOGLE_CHROME_BIN"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]

    for candidate in candidates:
        resolved = _resolve_binary_candidate(candidate)
        if resolved:
            return resolved
    return None


def _local_environment_checks() -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    py_ok = sys.version_info >= (3, 12)
    checks.append(
        _check(
            "python_version",
            py_ok,
            f"Detected Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )

    try:
        import kaleido  # type: ignore[import-untyped]  # noqa: F401

        checks.append(
            _check("kaleido_import", True, "kaleido import succeeded", "error")
        )
    except Exception as error:
        checks.append(
            _check("kaleido_import", False, _first_error_line(error), "error")
        )

    try:
        import plotly  # type: ignore[import-untyped]  # noqa: F401

        checks.append(_check("plotly_import", True, "plotly import succeeded", "error"))
    except Exception as error:
        checks.append(_check("plotly_import", False, _first_error_line(error), "error"))

    chrome_binary = _detect_chrome_binary()
    checks.append(
        _check(
            "chrome_binary",
            chrome_binary is not None,
            (
                f"Found browser binary at {chrome_binary}"
                if chrome_binary
                else "No Chrome/Chromium binary found in common locations"
            ),
            "error",
        )
    )

    databricks_env = [
        Environment.DATABRICKS_HOST,
        Environment.DATABRICKS_HTTP_PATH,
        Environment.DATABRICKS_ACCESS_TOKEN,
    ]
    missing = [env for env in databricks_env if not os.getenv(env)]
    checks.append(
        _check(
            "databricks_env",
            len(missing) == 0,
            (
                "All Databricks environment variables are set"
                if not missing
                else f"Missing Databricks env vars: {', '.join(missing)}"
            ),
            "warning",
        )
    )

    return checks


def _provider_checks(
    config_file: Path,
    registry_paths: Optional[List[Path]],
) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    try:
        raw_config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        config_registry = raw_config.get("registry")
        resolved_registry_paths = resolve_registry_paths(
            config_file=config_file,
            cli_registry_paths=registry_paths,
            config_registry=config_registry,
        )

        loader = ConfigLoader(
            yaml_path=config_file, registry_paths=resolved_registry_paths
        )
        presentation_config = PresentationConfig(**loader.config)
        provider_config_type = ProviderFactory.get_config_class(
            presentation_config.provider.type
        )
        provider_config_type(**presentation_config.provider.config)

        provider = ProviderFactory.create_provider(presentation_config.provider)
        checks.append(
            _check(
                "provider_init",
                True,
                f"Initialized provider '{presentation_config.provider.type}'",
                "error",
            )
        )
        for check_name, ok, detail in provider.run_preflight_checks():
            checks.append(_check(f"provider:{check_name}", ok, detail, "error"))
    except Exception as error:
        checks.append(
            _check(
                "provider_init",
                False,
                _first_error_line(error),
                "error",
            )
        )

    return checks


def doctor_command(
    config_file: Annotated[
        Optional[Path],
        typer.Option(
            "--config-file",
            "-c",
            help="Optional config file to run provider-level diagnostics",
        ),
    ] = None,
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
            help="Optional path to write a machine-readable doctor summary JSON file",
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
    """Run preflight diagnostics for local and provider/runtime dependencies."""
    started_at = now_iso8601_utc()
    checks: List[Dict[str, Any]] = []

    try:
        checks.extend(_local_environment_checks())
        if config_file is not None:
            checks.extend(_provider_checks(config_file, registry_paths))

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

        summary = {
            "command": "doctor",
            "status": status,
            "started_at": started_at,
            "completed_at": now_iso8601_utc(),
            "strict": strict,
            "config_file": str(config_file) if config_file else None,
            "checks": checks,
            "summary": {
                "total": len(checks),
                "passed": sum(1 for check in checks if check["ok"]),
                "failed_errors": len(error_failures),
                "failed_warnings": len(warning_failures),
            },
        }

        write_output_json(output_json, summary)

        for check in checks:
            icon = "✅" if check["ok"] else "❌"
            severity = check["severity"].upper()
            typer.echo(f"{icon} [{severity}] {check['name']}: {check['detail']}")

        if strict and error_failures:
            raise typer.Exit(1)

        return summary

    except typer.Exit:
        raise
    except Exception as error:
        error_code = resolve_cli_error_code(error, CliErrorCode.DOCTOR_FAILED)
        error_message = _first_error_line(error)
        payload = {
            "command": "doctor",
            "status": "error",
            "started_at": started_at,
            "completed_at": now_iso8601_utc(),
            "error": {"code": error_code, "message": error_message},
            "checks": checks,
        }
        write_output_json(output_json, payload)
        typer.echo(f"❌ [ERROR] doctor: {error_code} {error_message}")
        raise typer.Exit(1)
