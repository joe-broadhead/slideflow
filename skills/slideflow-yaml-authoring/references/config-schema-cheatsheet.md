# SlideFlow Config Schema Cheatsheet

## Root

```yaml
provider:
  type: "google_slides"
  config: {}

presentation:
  name: "Deck Name"
  slides: []

template_paths: []   # optional
registry: []         # optional
```

## Slide

```yaml
- id: "<slide-id>"
  title: "Optional title"
  replacements: []
  charts: []
```

## Replacement types

- `text`
- `table`
- `ai_text`

## Chart types

- `plotly_go`
- `template`
- `custom`

## Connector types

- `csv`
- `json`
- `databricks`
- `databricks_dbt`

## Parameter semantics

- `{param}`: runtime/CLI substitution token
- `{{PLACEHOLDER}}`: presentation placeholder token (preserved)
- `$column_name`: DataFrame column reference in chart/replacement config
