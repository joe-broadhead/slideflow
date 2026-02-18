---
name: slideflow-yaml-authoring
description: Generate and validate SlideFlow configuration YAML, choose chart strategy, and map Plotly options safely using SlideFlow contracts.
version: 1.0.0
spec: open-skill-v1
---

# SlideFlow YAML Authoring Skill

## Purpose

Use this skill to produce production-safe SlideFlow YAML configurations and chart
configs while preserving compatibility guarantees.

## Use this skill when

- building a new `config.yml` for SlideFlow
- translating reporting intent into connectors + replacements + charts
- deciding between `template`, `plotly_go`, and `custom` chart types
- validating YAML parameter contracts before runtime
- mapping Plotly configuration parameters into `traces` and `layout_config`

## Required inputs

- presentation intent (audience + desired slides)
- target provider configuration (`google_slides` settings)
- data source details (csv/json/databricks/dbt)
- template usage preference (`template` vs `plotly_go` vs `custom`)

## Deterministic workflow

1. Build root contract:
   - `provider`
   - `presentation.name`
   - `presentation.slides[]`
2. Add connectors and replacements with explicit names.
3. Select chart strategy:
   - use `template` for reusable patterns
   - use `plotly_go` for direct Plotly control
   - use `custom` only when required by specialized rendering logic
4. Validate references:
   - every `$column` maps to a real column
   - every registry function exists in `function_registry`
   - every required template parameter is present
5. Validate runtime safety:
   - preserve `{{PLACEHOLDER}}` tokens
   - use `{param}` only for CLI/runtime substitution
6. Run:
   - `slideflow validate config.yml`
   - `slideflow build config.yml --dry-run`

## Guardrails

- Never deprecate or remove existing features in generated output.
- Favor additive changes and deterministic behavior.
- Prefer built-in templates before generating custom one-off templates.
- Keep local template overrides explicit and intentional.

## Output contract

When producing config output, always include:

- complete YAML (no omitted required keys)
- a short assumptions list
- exact validation commands
- explicit note on whether templates are built-in or local

## References

- `references/config-schema-cheatsheet.md`
- `references/template-authoring-contract.md`
- `references/plotly-parameter-lookup.md`
- `assets/snippets/connectors.yml`
- `assets/snippets/replacements.yml`
- `assets/snippets/charts.yml`
