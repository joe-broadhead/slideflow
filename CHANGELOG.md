# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Google Docs provider support (`provider.type: google_docs`) with section-marker
  scoped rendering for replacements and charts.
- Google Sheets workbook support (`provider.type: google_sheets`) with workbook
  schema and dedicated CLI:
  - `slideflow sheets validate`
  - `slideflow sheets build`
  - `slideflow sheets doctor`
- Google Sheets tab-level write modes and idempotency model (`replace` / `append`)
  with metadata tracking and bounded parallel tab execution.
- Tab-local workbook AI summary schema (`workbook.tabs[].ai.summaries[]`) using
  `type: ai_text` + `config` pattern.
- Optional citation/provenance pipeline with top-level config:
  - `citations.enabled`
  - `citations.mode` (`model` | `execution` | `both`)
  - `citations.location` (`per_slide` | `per_section` | `document_end`)
  - `citations.max_items`
  - `citations.dedupe`
  - `citations.include_query_text`
- Citation rendering hooks for:
  - Google Slides speaker notes
  - Google Docs section footnotes/document-end sources
- Ownership handoff controls for Google Slides/Docs:
  - `provider.config.transfer_ownership_to`
  - `provider.config.transfer_ownership_strict`
- Chart image sharing-mode controls for Google Slides/Docs:
  - `provider.config.chart_image_sharing_mode` (`public` | `restricted`)
- Shared Google API utility layer for provider internals:
  - shared credential construction
  - shared rate-limited request execution helper
  - shared Drive image upload primitive
- Live Google Docs and Google Sheets test suites + manual workflows.
- Databricks AI provider (`provider: databricks`) for `ai_text` replacements
  via Databricks Serving Endpoints (OpenAI-compatible chat completions).
- Security/quality automation additions:
  - `CodeQL` workflow
  - `dependabot.yml` for pip + GitHub Actions updates
  - pre-commit hooks including `detect-secrets`
  - CI optional-connectors coverage path (BigQuery/DuckDB extras)
- New test coverage for:
  - auth utilities
  - rate limiter behavior
  - Google Drive ownership helpers
  - charts/workbook/sheets preflight/runtime helper paths
  - property-based data pipeline invariants

### Changed

- Build JSON output includes citation summary fields and per-result citation payloads.
- `slideflow sheets build` now executes workbook tabs with bounded parallel workers
  (`--threads`), capped by tab count.
- Sheets build runtime JSON now includes richer thread controls metadata:
  - `runtime.threads.supported_values`
  - `runtime.threads.effective_workers`
  - `runtime.threads.workload_size`
- Build JSON output includes ownership transfer status fields:
  - `ownership_transfer_attempted`
  - `ownership_transfer_succeeded`
  - `ownership_transfer_target`
  - `ownership_transfer_error`
- Source connectors expose citation entries across `csv`/`json`/`databricks`/`duckdb`/`dbt`.
- Packaging is modular for dbt/databricks stack:
  - base install excludes dbt/databricks-specific runtime dependencies
  - dbt/databricks usage requires connector extras
  - connectors now raise actionable install errors when optional dependencies are missing
- Runtime orchestration/refactor hardening:
  - `Presentation.render()` split into phased helper orchestration
  - replacement dispatch moved away from `hasattr` branching to explicit polymorphism
  - DBT warehouse connector execution flow deduplicated
  - legacy/dead chart upload paths removed in favor of active provider abstractions
  - chart rate limiting decoupled from provider-specific imports
  - runtime logging standardized across key modules
- CI/runtime quality hardening:
  - branch coverage enabled (`--cov-branch`) with fail-under staged to `82`
  - `pytest` strict markers enabled
  - release workflow enforces lockfile parity (`uv lock --check` + `uv sync --locked`)
- Reusable workflow now supports explicit install-extra selection via `slideflow-install-extras`.
- Google provider internals are consolidated to reduce duplicate auth/request/upload code.
- GitHub Actions runtime versions were refreshed:
  - `actions/checkout` `v4 -> v6`
  - `actions/setup-python` `v5 -> v6`
  - `actions/upload-pages-artifact` `v3 -> v4`
  - `astral-sh/setup-uv` `v5 -> v7`
- Docs were expanded/updated for:
  - Google Docs and Google Sheets providers
  - shared-drive/service-account operational patterns
  - CI quality and release quality controls
- Local contributor quality-gate commands in docs now consistently use `uv run ...`
  invocation patterns for lint/test/ABI checks.

### Fixed

- Exception chaining now preserves root causes in provider/auth error wrapping (`raise ... from error`).
- Citation validation no longer fails silently; malformed entries emit contextual warnings while rendering continues.
- Corrected malformed DBT warehouse YAML code fence rendering in config docs.
- Google Docs provider correctness fixes:
  - UTF-16 section offset handling
  - split-run marker handling
  - TOC duplication avoidance in contract checks
  - section marker removal finalization path
  - stable chart insertion ordering across repeated sections
- Google Sheets/workbook robustness fixes:
  - enforce explicit `target_tab` for `summary_tab` AI placement
  - prevent summary writes from clobbering source-tab data regions
  - tighten overlap/history/clear-range validation behavior
  - normalize non-finite decimal cell values
- Citation/speaker-notes rendering fixes for Slides notes index edge cases.
- Stabilized shared test-helper imports for direct `pytest` invocation by making
  `tests` an explicit package (`tests/__init__.py`).
- Unit-test dependency stubs now gracefully fall back when local NumPy/Pandas ABI
  mismatch warnings occur during import, reducing noisy local test output.
- NumPy/Pandas ABI compatibility checker now exercises `numpy.random` paths and
  prints `uv`-native remediation commands.

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
