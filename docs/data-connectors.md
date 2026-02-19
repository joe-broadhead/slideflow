# Data Connectors

SlideFlow supports four connector types for chart/replacement data sources:

- `csv`
- `json`
- `databricks`
- `databricks_dbt`

Use these in any `data_source` block for charts or replacements.

## Connector Matrix

| Type | Best for | Requires network | Required env vars |
| --- | --- | --- | --- |
| `csv` | local tabular files | no | none |
| `json` | local API exports/events | no | none |
| `databricks` | direct warehouse SQL | yes | `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_ACCESS_TOKEN` |
| `databricks_dbt` | dbt model SQL executed on Databricks | yes | same Databricks env vars (+ Git token env if needed) |

## CSV

```yaml
data_source:
  type: "csv"
  name: "sales_csv"
  file_path: "./data/sales.csv"
```

Notes:

- Uses `pandas.read_csv` with default parsing behavior.
- Relative paths resolve from your current execution directory.

## JSON

```yaml
data_source:
  type: "json"
  name: "events_json"
  file_path: "./data/events.json"
  orient: "records"
```

Supported `orient` values:

- `split`
- `records`
- `index`
- `columns`
- `values`
- `table`

If your JSON shape does not match `orient`, parsing fails.

## Databricks SQL

```yaml
data_source:
  type: "databricks"
  name: "warehouse_query"
  query: |
    SELECT month, revenue, target
    FROM mart.revenue_summary
    WHERE fiscal_quarter = '{quarter}'
```

Required environment:

```bash
export DATABRICKS_HOST="<workspace-hostname>"
export DATABRICKS_HTTP_PATH="<sql-warehouse-http-path>"
export DATABRICKS_ACCESS_TOKEN="<token>"
```

Tips:

- Keep SQL deterministic for reporting workflows.
- Limit columns to what chart/replacement logic needs.
- Prefer validated parameter substitution (`{quarter}` from batch params) over string concatenation.

## dbt on Databricks (`databricks_dbt`)

This connector compiles a dbt project, resolves a model's compiled SQL, then executes it on Databricks.

```yaml
data_source:
  type: "databricks_dbt"
  name: "dbt_model"
  model_alias: "monthly_revenue_by_region"
  package_url: "https://$GIT_TOKEN@github.com/org/analytics-dbt.git"
  project_dir: "/tmp/dbt_project_workspace"
  branch: "main"
  target: "prod"
  vars:
    start_date: "2026-01-01"
    end_date: "2026-01-31"
  profiles_dir: "/path/to/profiles"
  profile_name: "analytics"
```

Behavior highlights:

- Repositories are cloned under `project_dir/.slideflow_dbt_clones/<key>`.
- `project_dir` is treated as a workspace root, not a direct clone target.
- If `package_url` embeds `$TOKEN_NAME`, that env var must exist at runtime.

## Caching and Execution

SlideFlow caches connector fetches by config identity, which helps when:

- multiple charts use the same query/file in one run
- multiple replacements reuse one source

Treat connectors as read-only sources during a run for predictable results.

## Recommended Workflow

1. Start with local `csv`/`json` while designing charts and replacements.
2. Move to `databricks` once schema and logic are stable.
3. Move to `databricks_dbt` when business logic should live in dbt models.
4. Run `slideflow validate` before `slideflow build` in CI/CD.

## Troubleshooting

- File connector errors: check file existence and relative path assumptions.
- Databricks auth errors: verify all three Databricks env vars.
- dbt model not found: check `model_alias`, `branch`, and `target`.
- dbt Git clone fails: verify token variable in `package_url` and repo access.
