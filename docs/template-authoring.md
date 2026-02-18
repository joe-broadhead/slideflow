# Template Authoring

This guide defines the authoring contract for custom chart templates.

## File structure

A template file is YAML with metadata + template body:

```yaml
name: "My Template"
description: "What this template is for"
version: "1.0"
parameters:
  - name: "title"
    type: "string"
    required: true
    description: "Chart title"
template: |
  traces:
    - type: "bar"
      x: "${{ x_column }}"
      y: "${{ y_column }}"
  layout_config:
    title: "{{ title }}"
```

## Parameter rules

- `name`: unique parameter key.
- `type`: informational type label (`string`, `number`, `list`, etc.).
- `required`: required parameters must be provided in `template_config`.
- `default`: optional fallback when not provided.
- `description`: short contract documentation.

Missing required params fail fast with deterministic error messages.

## Column references

Use `${{ column_name_param }}` for chart data references. At render time this
becomes `$column_name` so SlideFlow maps to DataFrame columns.

## Jinja usage

`template` is rendered with Jinja2 and SlideFlow filter helpers. Keep expressions
simple and deterministic.

Good patterns:

- explicit defaults in parameter schema
- simple conditional labels
- stable trace/layout structures

Avoid:

- dynamic keys that change shape unpredictably
- business logic in templates (keep logic in data prep/registry)

## Naming and organization

Recommended category folders:

- `bars/`, `lines_areas/`, `composition/`, `distribution/`, `kpi_cards/`, `tables/`, `combo/`

Use path-qualified names in configs when possible (for example `bars/bar_basic`) to
avoid ambiguity.

## Precedence and overrides

Resolution order:

1. `template_paths` in config (in order)
2. `./templates`
3. `~/.slideflow/templates`
4. packaged built-ins

This allows project-local override of built-in templates without forking SlideFlow.

## Validation workflow

```bash
slideflow templates info bars/bar_basic
slideflow validate config.yml
slideflow build config.yml --dry-run
```
