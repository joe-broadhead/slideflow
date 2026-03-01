# Data Connectors

SlideFlow supports six connector types for chart/replacement data sources:

- `csv`
- `json`
- `databricks`
- `duckdb`
- `dbt` (composable, preferred)
- `databricks_dbt` (legacy, still supported)

Use these in any `data_source` block for charts or replacements.

For a step-by-step migration from legacy `databricks_dbt` to composable
`dbt`, see [DBT Migration Guide](dbt-migration.md).

## Installation extras

Install connector dependencies based on the connectors you use:

```bash
# Base package
pip install slideflow-presentations

# Databricks SQL connector
pip install "slideflow-presentations[databricks]"

# dbt connectors (includes dbt-core adapter stack + Git clone support)
pip install "slideflow-presentations[dbt]"

# Optional dbt warehouse backends
pip install "slideflow-presentations[bigquery]"
pip install "slideflow-presentations[duckdb]"
```

## Connector Matrix

| Type | Best for | Requires network | Required env vars |
| --- | --- | --- | --- |
| `csv` | local tabular files | no | none |
| `json` | local API exports/events | no | none |
| `databricks` | direct warehouse SQL | yes | `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_ACCESS_TOKEN` |
| `duckdb` | direct local/in-memory SQL | no | none |
| `dbt` | dbt model SQL executed on Databricks, BigQuery, or DuckDB (composable config) | yes/no (depends on warehouse and dbt repo) | Databricks env vars, BigQuery project/auth env vars, or none for local DuckDB (+ Git token env if needed) |
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
  # optional connector runtime overrides:
  # socket_timeout_s: 300
  # retry_max_attempts: 30
  # retry_max_duration_s: 900
  # retry_delay_min_s: 1
  # retry_delay_max_s: 60
```

Required environment:

```bash
export DATABRICKS_HOST="<workspace-hostname>"
export DATABRICKS_HTTP_PATH="<sql-warehouse-http-path>"
export DATABRICKS_ACCESS_TOKEN="<token>"
```

Optional Databricks connector runtime env tuning:

- `SLIDEFLOW_DATABRICKS_SOCKET_TIMEOUT_S`
- `SLIDEFLOW_DATABRICKS_RETRY_MAX_ATTEMPTS`
- `SLIDEFLOW_DATABRICKS_RETRY_MAX_DURATION_S`
- `SLIDEFLOW_DATABRICKS_RETRY_DELAY_MIN_S`
- `SLIDEFLOW_DATABRICKS_RETRY_DELAY_MAX_S`

Tips:

- Keep SQL deterministic for reporting workflows.
- Limit columns to what chart/replacement logic needs.
- Prefer validated parameter substitution (`{quarter}` from batch params) over string concatenation.

## DuckDB SQL

```yaml
data_source:
  type: "duckdb"
  name: "local_duckdb_query"
  database: "/tmp/analytics.duckdb" # optional; defaults to ':memory:'
  read_only: true # optional; defaults to true
  file_search_path: # optional; used for relative file references in DuckDB
    - "/tmp/data"
    - "/tmp/snapshots"
  query: |
    SELECT * FROM sales_summary
```

Notes:

- Install DuckDB runtime deps:
  `pip install "slideflow-presentations[duckdb]"`.
- `file_search_path` can be a list or a comma-separated string.
- If `file_search_path` is omitted, DuckDB uses its default file search behavior.

## dbt on Databricks (`dbt`, preferred)

This connector compiles a dbt project, resolves a model's compiled SQL, then executes it on Databricks.

```yaml
data_source:
  type: "dbt"
  name: "dbt_model"
  model_alias: "monthly_revenue_by_region"
  dbt:
    package_url: "https://$GIT_TOKEN@github.com/org/analytics-dbt.git"
    project_dir: "/tmp/dbt_project_workspace"
    branch: "main"
    target: "prod"
    vars:
      start_date: "2026-01-01"
      end_date: "2026-01-31"
    profiles_dir: "/path/to/profiles"
    profile_name: "analytics"
  warehouse:
    type: "databricks"
```

Behavior highlights:

- Repositories are cloned under `project_dir/.slideflow_dbt_clones/<key>`.
- `project_dir` is treated as a workspace root, not a direct clone target.
- If `package_url` embeds `$TOKEN_NAME`, that env var must exist at runtime.
- If `profiles_dir` is provided, SlideFlow copies profiles into the cloned dbt
  workspace and runs dbt with `--profiles-dir <clone_dir>`.
- If `profiles_dir` is omitted but the cloned repo contains `profiles.yml` at
  project root, SlideFlow auto-uses that project-root profiles file.
- Compile/dependency work for identical manifest cache keys is deduplicated
  across concurrent presentation threads in a single run.
- If multiple dbt nodes share `model_alias`, set one of:
  - `model_unique_id`
  - `model_package_name`
  - `model_selector_name`
  to avoid ambiguity errors.

## dbt on BigQuery (`dbt`)

This connector shape compiles a dbt project, resolves a model's compiled SQL,
then executes it on BigQuery.

```yaml
data_source:
  type: "dbt"
  name: "dbt_model_bigquery"
  model_alias: "monthly_revenue_by_region"
  dbt:
    package_url: "https://$GIT_TOKEN@github.com/org/analytics-dbt.git"
    project_dir: "/tmp/dbt_project_workspace"
    branch: "main"
    target: "prod"
    vars:
      start_date: "2026-01-01"
      end_date: "2026-01-31"
    profiles_dir: "/path/to/profiles"
    profile_name: "analytics"
  warehouse:
    type: "bigquery"
    project_id: "my-gcp-project" # optional if BIGQUERY_PROJECT/GOOGLE_CLOUD_PROJECT set
    location: "US" # optional
    credentials_path: "/path/to/service-account.json" # optional
    # credentials_json: '{"type":"service_account",...}' # optional alternative
```

BigQuery runtime options:

- Install BigQuery runtime dependencies:
  `pip install "slideflow-presentations[bigquery]"`.
- Set project id via:
  - `warehouse.project_id`, or
  - `BIGQUERY_PROJECT`, or
  - `GOOGLE_CLOUD_PROJECT`.
- Auth options:
  - `warehouse.credentials_path`, or
  - `warehouse.credentials_json`, or
  - Application Default Credentials (for example `GOOGLE_APPLICATION_CREDENTIALS`).

## dbt on DuckDB (`dbt`)

This connector shape compiles a dbt project, resolves a model's compiled SQL,
then executes it on DuckDB.

```yaml
data_source:
  type: "dbt"
  name: "dbt_model_duckdb"
  model_alias: "monthly_revenue_by_region"
  dbt:
    package_url: "https://$GIT_TOKEN@github.com/org/analytics-dbt.git"
    project_dir: "/tmp/dbt_project_workspace"
    branch: "main"
    target: "prod"
  warehouse:
    type: "duckdb"
    database: "/tmp/warehouse.duckdb" # required for dbt+duckdb
    read_only: true # optional; defaults to true
    file_search_path: # optional
      - "/tmp/dbt_project_workspace"
      - "/tmp/data"
```

## Legacy dbt on Databricks (`databricks_dbt`)

This legacy shape is still fully supported for backward compatibility.

```yaml
data_source:
  type: "databricks_dbt"
  name: "dbt_model_legacy"
  model_alias: "monthly_revenue_by_region"
  package_url: "https://$GIT_TOKEN@github.com/org/analytics-dbt.git"
  project_dir: "/tmp/dbt_project_workspace"
  branch: "main"
  target: "prod"
  vars:
    start_date: "2026-01-01"
    end_date: "2026-01-31"
```

## Caching and Execution

SlideFlow caches connector fetches by config identity, which helps when:

- multiple charts use the same query/file in one run
- multiple replacements reuse one source

Treat connectors as read-only sources during a run for predictable results.

Cache/compile tuning env vars:

- `SLIDEFLOW_DATA_CACHE_MAX_ENTRIES` (global source cache cap)
- `SLIDEFLOW_DBT_CACHE_MAX_ENTRIES` (default from built-in constants)
- `SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S`
- `SLIDEFLOW_DBT_FAILURE_CACHE_MAX_ENTRIES`

## Recommended Workflow

1. Start with local `csv`/`json` while designing charts and replacements.
2. Move to `duckdb` or `databricks` once schema and logic are stable.
3. Move to `dbt` when business logic should live in dbt models (`databricks_dbt` remains supported as legacy syntax).
4. Run `slideflow validate` before `slideflow build` in CI/CD.

## Troubleshooting

- File connector errors: check file existence and relative path assumptions.
- Databricks auth errors: verify all three Databricks env vars.
- dbt model not found: check `model_alias`, `branch`, and `target`.
- dbt alias ambiguity: add `model_unique_id`, `model_package_name`, or `model_selector_name`.
- dbt Git clone fails: verify token variable in `package_url` and repo access.
