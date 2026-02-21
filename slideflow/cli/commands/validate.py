"""Validate command implementation for configuration validation.

This module provides the validation functionality for Slideflow YAML
configurations and registry files. It performs comprehensive syntax
and semantic validation without executing any presentation generation,
making it ideal for configuration testing and development workflows.

Key Features:
    - YAML syntax and structure validation
    - Function registry resolution and validation
    - Pydantic model validation for presentation configurations
    - Parameter substitution testing
    - Detailed error reporting with helpful messages
    - Configuration summary display

The validation process includes:
    1. YAML file parsing and syntax checking
    2. Registry file loading and function resolution
    3. Parameter template validation
    4. Pydantic model validation for type safety
    5. Cross-reference validation between configuration sections

Example:
    Command-line usage::

        # Validate basic configuration
        slideflow validate config.yaml

        # Validate with custom registries
        slideflow validate config.yaml --registry custom.py

        # Validate with multiple registries
        slideflow validate config.yaml -r reg1.py -r reg2.py
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import typer
import yaml  # type: ignore[import-untyped]

from slideflow.cli.commands._registry import resolve_registry_paths
from slideflow.cli.error_codes import CliErrorCode, resolve_cli_error_code
from slideflow.cli.json_output import now_iso8601_utc, write_output_json
from slideflow.cli.theme import (
    print_config_summary,
    print_error,
    print_success,
    print_validation_header,
)
from slideflow.presentations.builder import PresentationBuilder
from slideflow.presentations.config import PresentationConfig
from slideflow.utilities import ConfigLoader

_GOOGLE_SLIDES_CONTRACT_FIELDS = (
    "slides(objectId,pageElements(shape(text(textElements(textRun(content))))))"
)


class ProviderContractValidationError(ValueError):
    """Raised when provider contract checks fail."""

    def __init__(self, message: str, summary: Dict[str, Any]):
        super().__init__(message)
        self.summary = summary


def _first_error_line(error: Exception) -> str:
    """Return a safe single-line error description."""
    text = str(error)
    if text:
        first_line = text.splitlines()[0]
        if first_line:
            return first_line
    return type(error).__name__


def _collect_expected_contract(
    presentation_config: PresentationConfig,
) -> Dict[str, Set[str]]:
    """Collect expected slide IDs and placeholder tokens from config."""
    expected: Dict[str, Set[str]] = {}
    slide_specs = list(getattr(presentation_config.presentation, "slides", []))

    for slide_spec in slide_specs:
        slide_id = getattr(slide_spec, "id", None)
        if not isinstance(slide_id, str) or not slide_id:
            continue

        placeholders: Set[str] = set()
        replacements = list(getattr(slide_spec, "replacements", []) or [])
        for replacement in replacements:
            replacement_config = getattr(replacement, "config", None)
            if not isinstance(replacement_config, dict):
                continue
            placeholder = replacement_config.get("placeholder")
            if isinstance(placeholder, str) and placeholder:
                placeholders.add(placeholder)

        slide_placeholders = expected.setdefault(slide_id, set())
        slide_placeholders.update(placeholders)

    return expected


def _read_template_ids_from_params(params_path: Path) -> List[str]:
    """Read unique template IDs from params CSV."""
    template_ids: Set[str] = set()

    with params_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "template_id" not in (reader.fieldnames or []):
            raise ValueError(
                f"Missing 'template_id' column in params file: {params_path}"
            )
        for row in reader:
            template_id = (row.get("template_id") or "").strip()
            if template_id:
                template_ids.add(template_id)

    if not template_ids:
        raise ValueError(
            f"No template_id values found in params file: {params_path}. "
            "Provide at least one template_id row."
        )

    return sorted(template_ids)


def _resolve_template_ids_for_contract_check(
    presentation_config: PresentationConfig, params_path: Optional[Path]
) -> List[str]:
    """Resolve template IDs from params CSV or provider config fallback."""
    if params_path is not None:
        return _read_template_ids_from_params(params_path)

    provider_config = getattr(presentation_config.provider, "config", {})
    if isinstance(provider_config, dict):
        template_id = provider_config.get("template_id")
        if isinstance(template_id, str) and template_id.strip():
            return [template_id.strip()]

    raise ValueError(
        "No template IDs available for provider contract check. "
        "Provide --params-path with a 'template_id' column or set "
        "provider.config.template_id."
    )


def _extract_slide_text_map(presentation_payload: Dict[str, Any]) -> Dict[str, str]:
    """Extract concatenated text content for each slide object ID."""
    slide_text_map: Dict[str, str] = {}
    slides = presentation_payload.get("slides", [])
    if not isinstance(slides, list):
        return slide_text_map

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("objectId")
        if not isinstance(slide_id, str) or not slide_id:
            continue

        chunks: List[str] = []
        page_elements = slide.get("pageElements", [])
        if isinstance(page_elements, list):
            for element in page_elements:
                if not isinstance(element, dict):
                    continue
                shape = element.get("shape")
                if not isinstance(shape, dict):
                    continue
                text = shape.get("text")
                if not isinstance(text, dict):
                    continue
                text_elements = text.get("textElements", [])
                if not isinstance(text_elements, list):
                    continue
                for text_element in text_elements:
                    if not isinstance(text_element, dict):
                        continue
                    text_run = text_element.get("textRun")
                    if not isinstance(text_run, dict):
                        continue
                    content = text_run.get("content")
                    if isinstance(content, str):
                        chunks.append(content)

        slide_text_map[slide_id] = "".join(chunks)

    return slide_text_map


def _run_google_provider_contract_check(
    presentation_config: PresentationConfig,
    provider: Any,
    params_path: Optional[Path],
) -> Dict[str, Any]:
    """Validate configured slide IDs/placeholders against Google Slides templates."""
    template_ids = _resolve_template_ids_for_contract_check(
        presentation_config, params_path
    )
    expected_contract = _collect_expected_contract(presentation_config)
    issues: List[Dict[str, Any]] = []
    slide_text_cache: Dict[str, Dict[str, str]] = {}
    checked_templates = 0

    for template_id in template_ids:
        slide_text_map = slide_text_cache.get(template_id)
        if slide_text_map is None:
            try:
                response = provider._execute_request(  # noqa: SLF001
                    provider.slides_service.presentations().get(
                        presentationId=template_id,
                        fields=_GOOGLE_SLIDES_CONTRACT_FIELDS,
                    )
                )
                slide_text_map = _extract_slide_text_map(response)
                slide_text_cache[template_id] = slide_text_map
                checked_templates += 1
            except Exception as error:
                issues.append(
                    {
                        "type": "template_fetch_failed",
                        "template_id": template_id,
                        "slide_id": None,
                        "placeholder": None,
                        "detail": _first_error_line(error),
                    }
                )
                continue

        for slide_id, placeholders in expected_contract.items():
            slide_text = slide_text_map.get(slide_id)
            if slide_text is None:
                issues.append(
                    {
                        "type": "missing_slide",
                        "template_id": template_id,
                        "slide_id": slide_id,
                        "placeholder": None,
                        "detail": "Slide id is not present in template presentation",
                    }
                )
                continue

            for placeholder in sorted(placeholders):
                if placeholder not in slide_text:
                    issues.append(
                        {
                            "type": "missing_placeholder",
                            "template_id": template_id,
                            "slide_id": slide_id,
                            "placeholder": placeholder,
                            "detail": "Placeholder not found on slide text",
                        }
                    )

    return {
        "enabled": True,
        "provider_type": presentation_config.provider.type,
        "checked_templates": checked_templates,
        "template_ids": template_ids,
        "checked_slides": sorted(expected_contract.keys()),
        "issues": issues,
    }


def validate_command(
    config_file: Path = typer.Argument(..., help="Path to YAML configuration file"),
    registry_paths: Optional[List[Path]] = typer.Option(
        None,
        "--registry",
        "-r",
        help="Path to Python registry files (can be used multiple times)",
    ),
    output_json: Optional[Path] = typer.Option(
        None,
        "--output-json",
        help="Optional path to write a machine-readable validation summary JSON file",
    ),
    params_path: Optional[Path] = typer.Option(
        None,
        "--params-path",
        "-f",
        help="Optional CSV file used for provider contract checks (expects template_id column)",
    ),
    provider_contract_check: bool = typer.Option(
        False,
        "--provider-contract-check",
        help="Run provider-aware contract checks (Google Slides slide IDs/placeholders)",
    ),
) -> None:
    """Validate YAML configuration and registry files.

    Performs comprehensive validation of Slideflow configuration files
    including YAML syntax, function registry resolution, and semantic
    validation using Pydantic models. This command helps identify
    configuration issues before attempting to build presentations.

    The validation process includes:
        1. YAML file existence and readability checks
        2. YAML syntax validation
        3. Registry file loading and function resolution
        4. Parameter template processing
        5. Pydantic model validation for type safety
        6. Configuration completeness verification

    Args:
        config_file: Path to the YAML configuration file to validate.
            Must be a readable file with valid YAML syntax.
        registry_paths: List of Python files containing function registries.
            Defaults to ["registry.py"]. These files are loaded to resolve
            function references in the configuration.

    Raises:
        typer.Exit: Exits with code 1 if validation fails at any stage.

    Examples:
        Basic validation::

            slideflow validate presentation.yaml

        With custom registry::

            slideflow validate config.yaml --registry custom_functions.py

        Multiple registries::

            slideflow validate config.yaml -r base.py -r custom.py

    Validation Checks:
        - File existence and permissions
        - YAML syntax correctness
        - Registry file validity and function availability
        - Parameter reference resolution
        - Data source configuration validity
        - Presentation structure completeness
        - Provider configuration correctness

    Output:
        On success, displays:
            - Validation success message
            - Configuration summary with key details
            - Slide count and structure information

        On failure, displays:
            - Detailed error message indicating the issue
            - File and line information when applicable
            - Suggestions for fixing common problems

    Note:
        - Validation does not perform actual data fetching or API calls
        - Registry functions are resolved but not executed
        - Template parameters are validated for syntax, not content
        - This command is safe to run in CI/CD pipelines
    """

    print_validation_header(str(config_file))
    run_started_at = now_iso8601_utc()
    provider_contract_summary: Optional[Dict[str, Any]] = None

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

        # Validate provider-specific configuration
        from slideflow.presentations.providers.factory import ProviderFactory

        ProviderFactory.get_config_class(presentation_config.provider.type)(
            **presentation_config.provider.config
        )

        # Validate chart/replacement specs deeply so unresolved function refs fail validation.
        for slide_spec in presentation_config.presentation.slides:
            PresentationBuilder._build_slide(slide_spec)

        if provider_contract_check:
            if presentation_config.provider.type != "google_slides":
                raise ValueError(
                    "Provider contract check is currently only supported for provider type 'google_slides'."
                )

            provider = ProviderFactory.create_provider(presentation_config.provider)
            provider_contract_summary = _run_google_provider_contract_check(
                presentation_config=presentation_config,
                provider=provider,
                params_path=params_path,
            )
            if provider_contract_summary["issues"]:
                raise ProviderContractValidationError(
                    "Provider contract validation failed. "
                    f"Found {len(provider_contract_summary['issues'])} issue(s).",
                    provider_contract_summary,
                )

        print_success()

        print_config_summary(presentation_config)

        slide_specs = list(getattr(presentation_config.presentation, "slides", []))

        def _safe_len(value: object) -> int:
            try:
                return len(value)  # type: ignore[arg-type]
            except TypeError:
                return 0

        total_slides = len(slide_specs)
        total_replacements = sum(
            _safe_len(getattr(slide_spec, "replacements", []))
            for slide_spec in slide_specs
        )
        total_charts = sum(
            _safe_len(getattr(slide_spec, "charts", [])) for slide_spec in slide_specs
        )
        presentation_name = str(getattr(presentation_config.presentation, "name", ""))
        write_output_json(
            output_json,
            {
                "command": "validate",
                "status": "success",
                "started_at": run_started_at,
                "completed_at": now_iso8601_utc(),
                "config_file": str(config_file),
                "registry_files": [str(path) for path in resolved_registry_paths],
                "summary": {
                    "provider_type": presentation_config.provider.type,
                    "presentation_name": presentation_name,
                    "slides": total_slides,
                    "replacements": total_replacements,
                    "charts": total_charts,
                },
                "provider_contract": provider_contract_summary,
            },
        )

    except Exception as e:
        error_code = resolve_cli_error_code(e, CliErrorCode.VALIDATE_FAILED)
        if isinstance(e, ProviderContractValidationError):
            provider_contract_summary = e.summary
        write_output_json(
            output_json,
            {
                "command": "validate",
                "status": "error",
                "started_at": run_started_at,
                "completed_at": now_iso8601_utc(),
                "config_file": str(config_file),
                "error": {"code": error_code, "message": _first_error_line(e)},
                "provider_contract": provider_contract_summary,
            },
        )
        print_error(str(e), error_code=error_code)
        raise typer.Exit(1)
