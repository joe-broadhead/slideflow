# Configuration Reference

## Top-level schema

```yaml
presentation:
  name: "Deck Name"
  name_fn: custom_name_fn # optional
  slides: [...]

provider:
  type: "google_slides"
  config: {...}

template_paths: ["./templates"] # optional additional paths (prepended before defaults)
registry: ["./registry.py"] # optional
```

## `presentation`

### Fields

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | `str` | yes | Output presentation name |
| `name_fn` | `callable` | no | Optional function to derive name |
| `slides` | `list[SlideSpec]` | yes | Ordered slide specs |

### `slides[]`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `str` | yes | Target slide ID in template |
| `title` | `str` | no | Metadata only |
| `replacements` | `list` | no | `text`, `table`, `ai_text` specs |
| `charts` | `list` | no | `plotly_go`, `template`, `custom` specs |

## `provider`

### `provider.type`

Supported values:

- `google_slides`

### `provider.config` for `google_slides`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `credentials` | `str` | conditionally | Path or raw JSON; can also come from env |
| `template_id` | `str` | recommended | Source template deck ID |
| `drive_folder_id` | `str` | no | Folder for uploaded chart images |
| `presentation_folder_id` | `str` | no | Folder for generated decks |
| `new_folder_name` | `str` | no | Create/use subfolder under `presentation_folder_id` |
| `new_folder_name_fn` | `callable` | no | Dynamic folder-name generator |
| `share_with` | `list[str]` | no | Emails to share generated deck with |
| `share_role` | `str` | no | `reader`, `writer`, or `commenter` |
| `requests_per_second` | `float` | no | API rate limit override |
| `strict_cleanup` | `bool` | no | Fail if temporary chart image cleanup fails |

For provider setup and operational behavior, see [Google Slides Provider](providers/google-slides.md).

## Replacements

All replacements follow:

```yaml
- type: "..."
  config: {...}
```

### `text`

```yaml
- type: "text"
  config:
    placeholder: "{{TOTAL}}"
    replacement: "42"
    data_source: {...}         # optional
    data_transforms: [...]     # optional
    value_fn: compute_total    # optional
    value_fn_args: {currency: "USD"}
```

### `table`

```yaml
- type: "table"
  config:
    prefix: "METRIC_"
    data_source: {...} # optional if static replacements provided
    replacements:      # optional static map
      "{{METRIC_1,1}}": "Revenue"
```

### `ai_text`

```yaml
- type: "ai_text"
  config:
    placeholder: "{{SUMMARY}}"
    prompt: "Summarize key insights"
    provider: "openai"          # or provider class/instance/callable
    provider_args:
      model: "gpt-4o"
    data_source: {...}            # optional (single or list)
```

For provider credentials and runtime options, see [AI Providers](ai-providers.md).

## Charts

All charts follow:

```yaml
- type: "..."
  config: {...}
```

Common positioning fields in chart config:

- `x`, `y`, `width`, `height`
- `dimensions_format`: `pt`, `emu`, `relative`, `expression`
- `alignment_format`: `left|center|right` + `top|center|bottom` (for example `center-top`)
- `scale`: image scaling factor
- `data_transforms`: optional ordered transform pipeline

### `plotly_go`

```yaml
- type: "plotly_go"
  config:
    title: "Revenue"
    data_source: {...}
    traces:
      - type: "bar"
        x: "$month"
        y: "$revenue"
    layout_config:
      yaxis:
        title: "USD"
```

### `template`

```yaml
- type: "template"
  config:
    template_name: "bars/bar_basic"
    template_config:
      title: "Monthly Revenue"
      x_column: "month"
      y_column: "revenue"
    data_source: {...}
```

### `custom`

```yaml
- type: "custom"
  config:
    chart_fn: build_custom_chart
    chart_config:
      variant: "stacked"
    data_source: {...}
```

## Data source configs

### CSV

```yaml
type: "csv"
name: "sales_csv"
file_path: "./data/sales.csv"
```

### JSON

```yaml
type: "json"
name: "events_json"
file_path: "./data/events.json"
orient: "records"
```

### Databricks SQL

```yaml
type: "databricks"
name: "warehouse_query"
query: "SELECT * FROM mart.sales LIMIT 100"
# optional connector runtime overrides:
# socket_timeout_s: 300
# retry_max_attempts: 30
# retry_max_duration_s: 900
# retry_delay_min_s: 1
# retry_delay_max_s: 60
```

Requires env vars:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

Optional per-source runtime tuning fields:

- `socket_timeout_s`
- `retry_max_attempts`
- `retry_max_duration_s`
- `retry_delay_min_s`
- `retry_delay_max_s`

### dbt on Databricks (composable, preferred)

```yaml
type: "dbt"
name: "dbt_model"
model_alias: "revenue_model"
dbt:
  package_url: "https://$GIT_TOKEN@github.com/org/repo.git"
  project_dir: "/tmp/dbt_project"
  branch: "main"
  target: "prod"
  vars:
    as_of_date: "2026-02-18"
warehouse:
  type: "databricks"
```

Optional alias disambiguation fields for `dbt`:

- `model_unique_id` (most specific)
- `model_package_name`
- `model_selector_name` (`node.name` in manifest)

Composable warehouse options:

- `warehouse.type`: `databricks` or `bigquery`
- `warehouse.project_id`: BigQuery project id override
- `warehouse.location`: optional warehouse location/region
- `warehouse.credentials_path`: optional path to BigQuery service-account JSON
- `warehouse.credentials_json`: optional inline service-account JSON payload

BigQuery variant example:

```yaml
type: "dbt"
name: "dbt_model_bigquery"
model_alias: "revenue_model"
dbt:
  package_url: "https://$GIT_TOKEN@github.com/org/repo.git"
  project_dir: "/tmp/dbt_project"
  branch: "main"
  target: "prod"
warehouse:
  type: "bigquery"
  project_id: "my-gcp-project"
  location: "US"
  credentials_path: "/path/to/service-account.json"
```

### Legacy dbt on Databricks (`databricks_dbt`)

```yaml
type: "databricks_dbt"
name: "dbt_model"
model_alias: "revenue_model"
package_url: "https://$GIT_TOKEN@github.com/org/repo.git"
project_dir: "/tmp/dbt_project"
branch: "main"
target: "prod"
vars:
  as_of_date: "2026-02-18"
```

Migration is non-breaking and optional. For side-by-side mapping and step-by-step
migration, see [DBT Migration Guide](dbt-migration.md).

For full connector behavior and runtime requirements, see [Data Connectors](data-connectors.md).

## Parameter substitution semantics

- `{param}` tokens are replaced from CLI batch params or loader params
- `{{PLACEHOLDER}}` tokens are preserved for slide/template replacement
- Mixed strings are supported (for example `"Q{quarter} {{TOTAL}}"`)

## Template paths and registries

- `template_paths`: additional chart-template search paths (highest precedence)
  - default fallbacks still apply: `./templates`, `~/.slideflow/templates`, packaged built-ins
- `registry`: one or many Python files exposing `function_registry`

For transform function contracts and examples, see [Data Transforms](data-transforms.md).
