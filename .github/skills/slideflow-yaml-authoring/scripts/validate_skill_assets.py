#!/usr/bin/env python3
"""Validate slideflow-yaml-authoring skill assets are current and coherent."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _load_yaml_mapping(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text())
    except Exception as exc:  # pragma: no cover - defensive
        errors.append(f"{path}: failed to parse YAML ({exc})")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{path}: expected top-level mapping")
        return {}
    return payload


def _validate_connectors(path: Path, errors: list[str]) -> None:
    payload = _load_yaml_mapping(path, errors)
    if not payload:
        return

    required = {
        "csv",
        "json",
        "databricks_sql",
        "dbt_preferred",
        "databricks_dbt_legacy",
    }
    _expect(required.issubset(payload.keys()), f"{path}: missing required connectors", errors)

    csv_conn = payload.get("csv", {})
    _expect(csv_conn.get("type") == "csv", f"{path}: csv.type must be csv", errors)
    _expect(bool(csv_conn.get("file_path")), f"{path}: csv.file_path missing", errors)

    dbt_conn = payload.get("dbt_preferred", {})
    _expect(dbt_conn.get("type") == "dbt", f"{path}: dbt_preferred.type must be dbt", errors)
    dbt_cfg = dbt_conn.get("dbt", {})
    _expect(isinstance(dbt_cfg, dict), f"{path}: dbt_preferred.dbt must be mapping", errors)
    _expect(bool(dbt_cfg.get("package_url")), f"{path}: dbt_preferred.dbt.package_url missing", errors)
    _expect(
        "$DBT_GIT_TOKEN" in str(dbt_cfg.get("package_url", "")),
        f"{path}: dbt_preferred.dbt.package_url should use $DBT_GIT_TOKEN",
        errors,
    )
    _expect(bool(dbt_cfg.get("project_dir")), f"{path}: dbt_preferred.dbt.project_dir missing", errors)
    warehouse = dbt_conn.get("warehouse", {})
    _expect(isinstance(warehouse, dict), f"{path}: dbt_preferred.warehouse must be mapping", errors)
    _expect(
        warehouse.get("type") == "databricks",
        f"{path}: dbt_preferred.warehouse.type must be databricks",
        errors,
    )

    legacy = payload.get("databricks_dbt_legacy", {})
    _expect(
        legacy.get("type") == "databricks_dbt",
        f"{path}: databricks_dbt_legacy.type must be databricks_dbt",
        errors,
    )


def _validate_replacements(path: Path, errors: list[str]) -> None:
    payload = _load_yaml_mapping(path, errors)
    if not payload:
        return

    required = {"text", "table", "ai_text_openai", "ai_text_databricks"}
    _expect(
        required.issubset(payload.keys()), f"{path}: missing required replacement snippets", errors
    )

    openai_cfg = payload.get("ai_text_openai", {}).get("config", {})
    _expect(
        openai_cfg.get("provider") == "openai",
        f"{path}: ai_text_openai.provider must be openai",
        errors,
    )

    databricks_cfg = payload.get("ai_text_databricks", {}).get("config", {})
    _expect(
        databricks_cfg.get("provider") == "databricks",
        f"{path}: ai_text_databricks.provider must be databricks",
        errors,
    )
    provider_args = databricks_cfg.get("provider_args", {})
    base_url = str(provider_args.get("base_url", ""))
    _expect("/serving-endpoints" in base_url, f"{path}: databricks base_url must contain /serving-endpoints", errors)
    _expect("/invocations" not in base_url, f"{path}: databricks base_url must not include /invocations", errors)


def _validate_charts(path: Path, errors: list[str]) -> None:
    payload = _load_yaml_mapping(path, errors)
    if not payload:
        return

    required = {"plotly_go", "template", "custom"}
    _expect(required.issubset(payload.keys()), f"{path}: missing required chart snippets", errors)

    plotly_cfg = payload.get("plotly_go", {}).get("config", {})
    _expect(isinstance(plotly_cfg.get("traces"), list), f"{path}: plotly_go.traces must be a list", errors)
    traces = plotly_cfg.get("traces", [])
    _expect(bool(traces), f"{path}: plotly_go.traces cannot be empty", errors)
    if traces:
        _expect(traces[0].get("type") == "bar", f"{path}: first plotly_go trace should be bar", errors)
    _expect("layout_config" in plotly_cfg, f"{path}: plotly_go.layout_config missing", errors)

    template_cfg = payload.get("template", {}).get("config", {})
    _expect(bool(template_cfg.get("template_name")), f"{path}: template.template_name missing", errors)
    _expect(isinstance(template_cfg.get("template_config"), dict), f"{path}: template.template_config must be mapping", errors)

    custom_cfg = payload.get("custom", {}).get("config", {})
    _expect(bool(custom_cfg.get("chart_fn")), f"{path}: custom.chart_fn missing", errors)


def _validate_plotly_index(path: Path, errors: list[str]) -> None:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc})")
        return

    metadata = payload.get("metadata", {})
    traces = payload.get("traces", {})
    layout = payload.get("layout", [])

    _expect(isinstance(metadata, dict) and bool(metadata), f"{path}: missing metadata", errors)
    _expect(isinstance(traces, dict) and bool(traces), f"{path}: traces payload missing or empty", errors)
    _expect(isinstance(layout, list) and len(layout) >= 10, f"{path}: layout property list too small", errors)

    _expect(bool(metadata.get("plotly_version")), f"{path}: metadata.plotly_version missing", errors)
    _expect(
        metadata.get("trace_count") == len(traces),
        f"{path}: metadata.trace_count does not match trace entries",
        errors,
    )
    _expect(
        metadata.get("layout_property_count") == len(layout),
        f"{path}: metadata.layout_property_count does not match layout length",
        errors,
    )
    generated_at = metadata.get("generated_at_utc")
    if generated_at is not None:
        _expect(
            isinstance(generated_at, str) and bool(generated_at.strip()),
            f"{path}: metadata.generated_at_utc must be a non-empty string when present",
            errors,
        )

    required_traces = {"bar", "scatter", "pie", "table"}
    missing_traces = sorted(required_traces - set(traces.keys()))
    _expect(
        not missing_traces,
        f"{path}: missing trace entries: {', '.join(missing_traces)}" if missing_traces else "",
        errors,
    )

    for name, props in traces.items():
        _expect(isinstance(props, list) and len(props) >= 5, f"{path}: trace `{name}` has too few properties", errors)
        _expect(props != ["type"], f"{path}: trace `{name}` unresolved (only `type` present)", errors)


def _validate_example_config(
    path: Path,
    expected_provider: str,
    example_dir: Path,
    errors: list[str],
) -> None:
    payload = _load_yaml_mapping(path, errors)
    if not payload:
        return

    provider = payload.get("provider", {})
    _expect(isinstance(provider, dict), f"{path}: provider must be mapping", errors)
    _expect(provider.get("type") == expected_provider, f"{path}: provider.type must be {expected_provider}", errors)

    if expected_provider in {"google_slides", "google_docs"}:
        presentation = payload.get("presentation", {})
        _expect(isinstance(presentation, dict), f"{path}: presentation must be mapping", errors)
        slides = presentation.get("slides", [])
        _expect(isinstance(slides, list) and bool(slides), f"{path}: presentation.slides must be non-empty list", errors)
        if slides:
            _expect(bool(slides[0].get("id")), f"{path}: first slide id missing", errors)
            charts = slides[0].get("charts", [])
            if charts:
                ds = charts[0].get("config", {}).get("data_source", {})
                file_path = ds.get("file_path")
                if file_path:
                    target = (example_dir / file_path).resolve()
                    _expect(target.exists(), f"{path}: referenced file_path not found: {file_path}", errors)

    if expected_provider == "google_sheets":
        workbook = payload.get("workbook", {})
        _expect(isinstance(workbook, dict), f"{path}: workbook must be mapping", errors)
        tabs = workbook.get("tabs", [])
        _expect(isinstance(tabs, list) and bool(tabs), f"{path}: workbook.tabs must be non-empty list", errors)
        if tabs:
            mode = tabs[0].get("mode")
            _expect(mode in {"replace", "append", "update"}, f"{path}: invalid tab mode `{mode}`", errors)
            ds = tabs[0].get("data_source", {})
            file_path = ds.get("file_path")
            if file_path:
                target = (example_dir / file_path).resolve()
                _expect(target.exists(), f"{path}: referenced file_path not found: {file_path}", errors)


def _validate_examples(root: Path, errors: list[str]) -> None:
    example_dir = root / "assets" / "examples"
    slides = example_dir / "slides.minimal.yml"
    docs = example_dir / "docs.minimal.yml"
    sheets = example_dir / "sheets.minimal.yml"
    sample_csv = example_dir / "sample_metrics.csv"
    expected_outputs = example_dir / "expected-command-output.md"

    for path in [slides, docs, sheets, sample_csv, expected_outputs]:
        _expect(path.exists(), f"{path}: required example asset missing", errors)

    if slides.exists():
        _validate_example_config(slides, "google_slides", example_dir, errors)
    if docs.exists():
        _validate_example_config(docs, "google_docs", example_dir, errors)
    if sheets.exists():
        _validate_example_config(sheets, "google_sheets", example_dir, errors)

    if sample_csv.exists():
        lines = sample_csv.read_text().strip().splitlines()
        _expect(len(lines) >= 2, f"{sample_csv}: must include header and at least one data row", errors)
        _expect(lines[0] == "month,revenue", f"{sample_csv}: unexpected header (expected month,revenue)", errors)

    if expected_outputs.exists():
        content = expected_outputs.read_text()
        required_tokens = [
            "slides.minimal.yml",
            "docs.minimal.yml",
            "sheets.minimal.yml",
            "slideflow doctor --config-file",
            "slideflow validate",
            "slideflow build",
            "slideflow sheets doctor",
            "slideflow sheets validate",
            "slideflow sheets build",
            "--output-json",
        ]
        for token in required_tokens:
            _expect(token in content, f"{expected_outputs}: missing `{token}`", errors)


def _validate_markdown_contracts(root: Path, errors: list[str]) -> None:
    skill_md = root / "SKILL.md"
    command_matrix = root / "references" / "provider-command-matrix.md"
    ai_cheatsheet = root / "references" / "ai-provider-cheatsheet.md"
    citations = root / "references" / "citations.md"
    sheets_modes = root / "references" / "sheets-modes.md"

    skill_text = skill_md.read_text()
    for token in [
        "provider-command-matrix.md",
        "ai-provider-cheatsheet.md",
        "citations.md",
        "sheets-modes.md",
        "google_slides",
        "google_docs",
        "google_sheets",
    ]:
        _expect(token in skill_text, f"{skill_md}: missing required reference `{token}`", errors)

    matrix_text = command_matrix.read_text()
    for token in [
        "slideflow doctor --config-file",
        "slideflow validate config.yml --provider-contract-check",
        "slideflow sheets doctor config.yml --strict",
        "slideflow sheets validate config.yml",
        "slideflow sheets build config.yml --threads 10",
        "assets/examples/slides.minimal.yml",
        "assets/examples/docs.minimal.yml",
        "assets/examples/sheets.minimal.yml",
    ]:
        _expect(token in matrix_text, f"{command_matrix}: missing `{token}`", errors)

    ai_text = ai_cheatsheet.read_text()
    for token in [
        "provider: databricks",
        "/serving-endpoints",
        "DATABRICKS_TOKEN",
    ]:
        _expect(token in ai_text, f"{ai_cheatsheet}: missing `{token}`", errors)

    citations_text = citations.read_text()
    for token in ["citations:", "per_slide", "slideflow validate config.yml --provider-contract-check"]:
        _expect(token in citations_text, f"{citations}: missing `{token}`", errors)

    sheets_text = sheets_modes.read_text()
    for token in ["replace", "append", "update", "slideflow sheets doctor config.yml --strict"]:
        _expect(token in sheets_text, f"{sheets_modes}: missing `{token}`", errors)


def main() -> int:
    root = _skill_root()
    errors: list[str] = []

    _validate_connectors(root / "assets" / "snippets" / "connectors.yml", errors)
    _validate_replacements(root / "assets" / "snippets" / "replacements.yml", errors)
    _validate_charts(root / "assets" / "snippets" / "charts.yml", errors)
    _validate_markdown_contracts(root, errors)
    _validate_examples(root, errors)
    _validate_plotly_index(root / "references" / "plotly-reference-index.json", errors)

    if errors:
        print("Skill asset validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Skill asset validation passed.")
    print(f"Validated skill directory: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

