# Slideflow Config Schema Cheatsheet

## Root contracts by artifact kind

### Google Slides

```yaml
provider:
  type: google_slides
  config: {}

presentation:
  name: "Deck Name"
  slides: []

template_paths: []   # optional
registry: []         # optional
```

### Google Docs

```yaml
provider:
  type: google_docs
  config: {}

presentation:
  name: "Doc Name"
  slides: []         # section marker ids for docs provider

registry: []
```

### Google Sheets

```yaml
provider:
  type: google_sheets
  config: {}

workbook:
  title: "Workbook Name"
  tabs: []

registry: []
```

## Slide/Tab units

### Slides/Docs section

```yaml
- id: "<slide-object-id-or-doc-section-marker>"
  replacements: []
  charts: []
```

### Sheets tab

```yaml
- name: "tab_name"
  mode: replace   # replace|append
  start_cell: A1
  include_header: true
  data_source: {}
  data_transforms: []
  ai:
    summaries: []
```

## Replacement types

- `text`
- `table`
- `ai_text`

## Chart types

- `plotly_go`
- `template`
- `custom`

## Data source types

- `csv`
- `json`
- `databricks`
- `duckdb`
- `dbt` (preferred for new dbt development)
- `databricks_dbt` (legacy-compatible)

## Preferred dbt shape

```yaml
data_source:
  type: dbt
  name: dbt_model
  model_alias: slide__example_model
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/repo.git
    project_dir: /tmp/dbt_project
    branch: main
    target: prod
    vars:
      time_period: weekly
  warehouse:
    type: databricks
```

## Token semantics

- `{param}`: runtime substitution token
- `{{PLACEHOLDER}}`: presentation placeholder token (preserved)
- `$column_name`: DataFrame column reference
