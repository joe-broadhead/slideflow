# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Additive composable DBT connector config (`type: dbt`) with nested `dbt` + `warehouse` blocks.
- Dedicated DBT migration guide with side-by-side legacy/composable examples and explicit selector disambiguation guidance.

### Changed

- Documentation now treats `type: dbt` as the preferred DBT config shape while keeping `databricks_dbt` documented as legacy-compatible syntax.
- Explicit compatibility statement: `databricks_dbt` remains supported and migration to `dbt` is optional/non-breaking.

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
