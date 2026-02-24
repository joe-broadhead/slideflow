# DBT Migration Guide

This guide explains how to move from legacy `type: databricks_dbt` configs to
composable `type: dbt` configs, while keeping compatibility safe.

## Compatibility Contract

- `type: databricks_dbt` remains supported.
- `type: dbt` is the preferred shape for new development.
- Migration is optional and non-breaking.

## Side-by-Side Configs

Legacy (still supported):

```yaml
data_source:
  type: databricks_dbt
  name: revenue_model
  model_alias: slide__monthly_revenue
  package_url: https://$DBT_GIT_TOKEN@github.com/org/analytics-dbt.git
  project_dir: /tmp/dbt_project
  branch: main
  target: prod
  vars:
    as_of_date: "{as_of_date}"
  profiles_dir: /workspace/dbt/profiles
  profile_name: analytics
```

Composable (preferred):

```yaml
data_source:
  type: dbt
  name: revenue_model
  model_alias: slide__monthly_revenue
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/analytics-dbt.git
    project_dir: /tmp/dbt_project
    branch: main
    target: prod
    vars:
      as_of_date: "{as_of_date}"
    profiles_dir: /workspace/dbt/profiles
    profile_name: analytics
  warehouse:
    type: databricks
```

## Field Mapping

| Legacy (`databricks_dbt`) | Composable (`dbt`) |
| --- | --- |
| `type: databricks_dbt` | `type: dbt` + `warehouse.type: databricks` |
| `model_alias` | `model_alias` |
| `package_url` | `dbt.package_url` |
| `project_dir` | `dbt.project_dir` |
| `branch` | `dbt.branch` |
| `target` | `dbt.target` |
| `vars` | `dbt.vars` |
| `profiles_dir` | `dbt.profiles_dir` |
| `profile_name` | `dbt.profile_name` |

## Migration Steps

1. Copy your existing `databricks_dbt` block.
2. Change `type` from `databricks_dbt` to `dbt`.
3. Move dbt project fields under a new `dbt:` block.
4. Add `warehouse:` with `type: databricks`.
5. Run `slideflow validate ...` and then `slideflow build ...`.
6. Keep one stable `databricks_dbt` config in CI until the migrated config is proven.

## Alias Ambiguity and Disambiguation

If multiple dbt nodes share the same alias, SlideFlow now raises an explicit
ambiguity error and asks you to disambiguate.

Available selectors:

- `model_unique_id` (most specific)
- `model_package_name`
- `model_selector_name` (`node.name` in manifest)

Example:

```yaml
data_source:
  type: dbt
  name: revenue_model
  model_alias: slide__monthly_revenue
  model_unique_id: model.analytics.slide__monthly_revenue
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/analytics-dbt.git
    project_dir: /tmp/dbt_project
  warehouse:
    type: databricks
```

## Auth and Environment Expectations

Databricks execution (`warehouse.type: databricks`):

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

BigQuery execution (`warehouse.type: bigquery`):

- project id from one of:
  - `warehouse.project_id`
  - `BIGQUERY_PROJECT`
  - `GOOGLE_CLOUD_PROJECT`
- auth from one of:
  - `warehouse.credentials_path`
  - `warehouse.credentials_json`
  - Application Default Credentials (for example `GOOGLE_APPLICATION_CREDENTIALS`)

## Common Migration Errors

- `Ambiguous dbt model alias ...`
  - Add `model_unique_id`, `model_package_name`, or `model_selector_name`.
- `dbt compile failed: Path '/home/runner/.dbt' does not exist`
  - Set `dbt.profiles_dir` or ensure `profiles.yml` exists in dbt project root.
- `Missing BigQuery project id ...`
  - Set `warehouse.project_id` or BigQuery project env vars.

## See Also

- [Data Connectors](data-connectors.md)
- [Configuration Reference](config-reference.md)
- [Troubleshooting](troubleshooting.md)
