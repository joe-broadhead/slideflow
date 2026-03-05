---
name: slideflow-yaml-authoring
description: Author and validate production-safe Slideflow YAML for Google Slides, Google Docs, and Google Sheets, including composable dbt connectors and AI providers.
version: 2.0.0
spec: open-skill-v1
---

# Slideflow YAML Authoring Skill

## Purpose

Use this skill to produce production-safe Slideflow YAML and deterministic run
commands across artifact kinds (`slides`, `docs`, `sheets`).

Supported provider ids:

- `google_slides`
- `google_docs`
- `google_sheets`

## Use this skill when

- creating or editing Slideflow config for Google Slides, Docs, or Sheets
- translating reporting intent into data sources, transforms, replacements, and charts
- selecting between `template`, `plotly_go`, and `custom` charts
- defining AI summaries/replacements across providers (OpenAI, Gemini, Databricks serving)
- validating provider contracts before runtime failures

## Required inputs

- target artifact kind (`slides`, `docs`, or `sheets`)
- provider configuration (template id/folder ids/credentials behavior)
- data source details (dbt/warehouse or direct sql/csv/json)
- runtime parameter shape (`{param}` tokens and optional params CSV)
- preferred AI provider (if AI summaries are required)

## Deterministic workflow

1. Build the root contract for the artifact kind.
2. Define data sources with explicit names.
3. Prefer `type: dbt` + `dbt:` + `warehouse:` for new work.
4. Add replacements/charts (or workbook tabs for sheets) with explicit function names.
5. Validate references:
   - `$column` references map to real output columns.
   - every `*_fn` exists in `function_registry`.
   - template ids/placeholders/markers are valid for provider.
6. Run commands from `references/provider-command-matrix.md`.
7. Run gotchas pass from `references/gotchas.md`.

## Guardrails

- Prefer additive, backward-compatible changes.
- Keep legacy `databricks_dbt` examples clearly marked as legacy-only.
- Keep secrets in env vars; never hardcode credentials/token values.
- Use explicit template ids and registry paths when ambiguous.
- For Databricks serving AI provider, use serving-endpoints base URL (not `/invocations`).
- For Google Sheets, define tab `mode` intentionally (`replace`, `append`, `update`).
- For citations-enabled slides configs, keep source metadata stable and deterministic.

## Output contract

When producing config output, include:

- complete YAML for the selected artifact kind
- assumptions list (provider, runtime params, env vars)
- exact `doctor`/`validate`/`build` commands
- env var contract for data + AI provider
- note on whether templates are built-in or local

## References

- `references/config-schema-cheatsheet.md`
- `references/provider-command-matrix.md`
- `references/ai-provider-cheatsheet.md`
- `references/citations.md`
- `references/sheets-modes.md`
- `references/template-authoring-contract.md`
- `references/plotly-parameter-lookup.md`
- `references/gotchas.md`
- `assets/snippets/connectors.yml`
- `assets/snippets/replacements.yml`
- `assets/snippets/charts.yml`
- `assets/examples/`
