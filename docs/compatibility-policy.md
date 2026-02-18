# Compatibility Policy

SlideFlow follows a feature-preservation policy for this program of work.

## Core commitments

1. Brand, repository, and docs remain `Slideflow`.
2. PyPI distribution name is `slideflow-presentations`.
3. Import namespace remains `slideflow`.
4. CLI command remains `slideflow`.
5. Existing feature surface stays supported.

## Change rules

1. No feature deprecation/removal without an explicitly approved phase.
2. Behavior changes must be additive by default.
3. Security/bug fixes are allowed when required for correctness or safety.
4. Any behavior-impacting change must ship with:
   - regression tests
   - release note/doc updates
   - CI validation in PR

## Regression coverage expectations

Compatibility checks must continue to cover:

- CLI command and option availability
- Data connectors (`csv`, `json`, `databricks`, `databricks_dbt`)
- Replacements (`text`, `table`, `ai_text`)
- Charts (`plotly_go`, `custom`, `template`)
- Template engine and registry resolution behavior

## Enforcement

PRs are expected to pass:

- format checks
- lint checks
- type checks
- tests with coverage floor

Changes that break compatibility expectations require explicit approval and a dedicated migration plan.
