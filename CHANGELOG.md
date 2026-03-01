# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Optional citation/provenance pipeline for rendered outputs with top-level config:
  - `citations.enabled`
  - `citations.mode` (`model` | `execution` | `both`)
  - `citations.location` (`per_slide` | `per_section` | `document_end`)
  - `citations.max_items`
  - `citations.dedupe`
  - `citations.include_query_text`
- Citation rendering hooks:
  - Google Slides speaker-notes `Sources` rendering
  - Google Docs section footnote or document-end `Sources` rendering
- Ownership handoff controls for Google Slides/Docs providers:
  - `provider.config.transfer_ownership_to`
  - `provider.config.transfer_ownership_strict`
- Chart image sharing-mode controls for Google Slides/Docs providers:
  - `provider.config.chart_image_sharing_mode` (`public` | `restricted`)
- Shared Google API utility layer for provider internals:
  - shared service-account credential construction
  - shared rate-limited request execution helper
  - shared Drive image upload primitive
- Dedicated CI optional-connectors coverage path (BigQuery/DuckDB extras).
- New targeted test coverage for:
  - auth utilities
  - rate limiter behavior
  - Google Drive ownership helper utilities
  - extracted chart/workbook/sheets preflight helper paths

### Changed

- Build JSON output includes citation summary fields and per-result citation payloads.
- Build JSON output includes ownership transfer status fields:
  - `ownership_transfer_attempted`
  - `ownership_transfer_succeeded`
  - `ownership_transfer_target`
  - `ownership_transfer_error`
- Source connectors expose citation entries across `csv`/`json`/`databricks`/`duckdb`/`dbt`.
- Packaging is now modular for dbt/databricks stack:
  - base install excludes dbt/databricks-specific runtime dependencies
  - dbt/databricks usage requires connector extras
  - connectors now raise actionable install errors when optional dependencies are missing
- Release workflow now enforces lockfile parity with CI (`uv lock --check` + `uv sync --locked`).
- Reusable workflow now supports explicit install-extra selection via `slideflow-install-extras`.
- Charts now use a provider-neutral presentation rate limiter utility (no provider-module coupling).
- Google provider internals have been consolidated to reduce duplicate auth/request/upload code.
- High-complexity runtime methods were split into smaller helpers in:
  - `slideflow/presentations/charts.py`
  - `slideflow/workbooks/builder.py`
  - `slideflow/workbooks/providers/google_sheets.py`

### Fixed

- Exception chaining now preserves root causes in provider/auth error wrapping (`raise ... from error`).
- Citation validation no longer fails silently; malformed entries emit contextual warnings while rendering continues.
- Corrected malformed DBT warehouse YAML code fence rendering in docs config reference.

## [0.0.6] - 2026-02-26

### Added

- Additive composable DBT connector config (`type: dbt`) with nested `dbt` + `warehouse` blocks.
- Warehouse execution abstraction for DBT-compiled SQL and pluggable warehouse backends.
- BigQuery SQL executor support for composable DBT sources (`warehouse.type: bigquery`).
- DuckDB connector support and DBT DuckDB warehouse routing (`warehouse.type: duckdb`).
- Deterministic DBT manifest model resolution index with explicit disambiguation selectors:
  - `model_unique_id`
  - `model_package_name`
  - `model_selector_name`
- Bounded data-source cache controls via `SLIDEFLOW_DATA_CACHE_MAX_ENTRIES`.
- Dedicated DBT migration guide with side-by-side legacy/composable examples and explicit selector disambiguation guidance.
- NumPy/Pandas ABI compatibility checker script (`scripts/ci/check_numpy_binary_compatibility.py`) enforced in CI/release workflows.
- Actionlint CI validation for GitHub workflow syntax/runtime safety checks.

### Changed

- `databricks_dbt` remains supported and now runs through the composable DBT runtime path for backward-compatible behavior.
- Databricks connector now supports explicit timeout/retry tuning and typed error categories.
- Release workflow is idempotent for reruns:
  - skips PyPI publish when version already exists
  - skips tag/release creation when already present
- Reusable workflow now supports BigQuery/ADC secret mapping:
  - `BIGQUERY_PROJECT`
  - `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- Documentation now treats `type: dbt` as the preferred DBT config shape while keeping `databricks_dbt` as legacy-compatible syntax.

### Fixed

- Safer first-line error extraction across CLI/connector paths to avoid empty-message indexing failures.
- Safer CLI command option defaults for both CLI and programmatic invocation paths.
- DBT manifest lookup now fails deterministically on alias collisions with actionable selector guidance.
- DBT/data cache behavior hardened for concurrent builds to reduce duplicate compile/fetch work.
- Registry module loading is now thread-safe during concurrent builds, preventing transient import-state collisions when multiple workers resolve registries at once.
- Reusable workflow configuration now avoids invalid `secrets` expression usage in step-level conditions, preventing workflow-file validation failures on push events.
- Reusable workflow trigger/input parsing validation hardened for safer dispatch and caller compatibility.

## [0.0.5] - 2026-02-21

### Added

- `slideflow doctor` CLI preflight command with strict mode and machine-readable JSON output.
- Reusable workflow outputs for structured JSON results:
  - `doctor-result-json`
  - `validate-result-json`
  - `build-result-json`

### Changed

- Reusable workflow now supports provider contract checks during validate.
- Documentation expanded for deployments, automation outputs, testing, and release operations.

### Fixed

- DBT manifest compile cache concurrency hardening to avoid duplicate compile/deps work for the same key during parallel deck builds.
- DBT profile resolution behavior for project-root `profiles.yml` in cloned repos.
- Safer first-line error extraction in CLI error reporting paths to avoid empty-message indexing issues.

## [0.0.4] - 2026-02-19

### Notes

- Baseline published release prior to current unreleased changes.
