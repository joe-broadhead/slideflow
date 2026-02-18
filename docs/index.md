# SlideFlow

SlideFlow generates Google Slides decks from structured YAML, data sources, and reusable chart/replacement logic.

## Core capabilities

- Declarative presentation builds via `slideflow build`
- Fast preflight validation via `slideflow validate`
- Data connectors for CSV, JSON, Databricks SQL, and dbt-on-Databricks
- Dynamic replacements (`text`, `table`, `ai_text`)
- Charts via Plotly graph objects, reusable templates, or custom Python functions
- Batch deck generation with `--params-path` for high-volume reporting

## Recommended workflow

1. Configure auth and template IDs in [Getting Started](getting-started.md).
2. Run the full local path in [Quickstart](quickstart.md).
3. Use [CLI Reference](cli-reference.md) and [Configuration Reference](config-reference.md) for production configs.
4. Use [Security & Auth](security.md), [Testing](testing.md), and [Release Process](release-process.md) for operational hardening.

## Quality policy

- All release-bound changes should include tests.
- Validation must pass before build in local and CI workflows.
