# Automation

Use Slideflow's reusable workflow to run scheduled presentation/doc/workbook builds for business teams.

## Reusable Workflow

Workflow path:

`/.github/workflows/reusable-slideflow-build.yml`

You can call it from another repo with:

```yaml
uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
```

## Scheduled Caller Example

```yaml
name: Weekly Business Slides

on:
  schedule:
    - cron: "0 13 * * 1" # Mondays at 13:00 UTC
  workflow_dispatch:

jobs:
  weekly-slides:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets:
      GOOGLE_SLIDEFLOW_CREDENTIALS: ${{ secrets.GOOGLE_SLIDEFLOW_CREDENTIALS }}
      DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
      DATABRICKS_HTTP_PATH: ${{ secrets.DATABRICKS_HTTP_PATH }}
      DATABRICKS_ACCESS_TOKEN: ${{ secrets.DATABRICKS_ACCESS_TOKEN }}
      DBT_GIT_TOKEN: ${{ secrets.DBT_GIT_TOKEN }} # optional; for private dbt/databricks_dbt repos
      DBT_ACCESS_TOKEN: ${{ secrets.DBT_ACCESS_TOKEN }} # optional; falls back to DBT_GIT_TOKEN in reusable workflow
      DBT_ENV_SECRET_GIT_CREDENTIAL: ${{ secrets.DBT_ENV_SECRET_GIT_CREDENTIAL }} # optional; falls back to DBT_ACCESS_TOKEN, then DBT_GIT_TOKEN
      BIGQUERY_PROJECT: ${{ secrets.BIGQUERY_PROJECT }} # optional; for warehouse.type=bigquery
      GOOGLE_APPLICATION_CREDENTIALS_JSON: ${{ secrets.GOOGLE_APPLICATION_CREDENTIALS_JSON }} # optional; writes ADC credentials file
    with:
      config-file: config/weekly_exec_report.yml
      artifact-kind: presentation
      registry-files: |
        registries/base_registry.py
        registries/team_registry.py
      params-path: config/weekly_variants.csv
      run-doctor: true
      strict-doctor: true
      run-validate: true
      run-provider-contract-check: true
      threads: "2"
      requests-per-second: "1.0"
      upload-log-artifact: true
      artifact-name: weekly-slideflow-logs
```

## Inputs

- `config-file` (required): Path to Slideflow YAML config.
- `artifact-kind` (optional): `presentation` (default) or `sheets`.
- `registry-files` (optional): Comma/newline-separated registry file paths.
- `params-path` (optional): CSV file for multi-variant builds.
- `working-directory` (optional): Command working directory. Default `.`.
- `python-version` (optional): Python version. Default `3.12`.
- `slideflow-package-spec` (optional): Package to install. Default `slideflow-presentations`.
- `extra-pip-packages` (optional): Newline-separated additional packages.
- `run-pip-check` (optional): Run `pip check`. Default `true`.
- `run-doctor` (optional): Run preflight doctor before validate/build (`slideflow doctor` for `presentation`, `slideflow sheets doctor` for `sheets`). Default `true`.
- `strict-doctor` (optional): Make doctor fail on error-severity findings. Default `false`.
- `run-validate` (optional): Run validate before build (`slideflow validate` for `presentation`, `slideflow sheets validate` for `sheets`). Default `true`.
- `run-provider-contract-check` (optional): Add `--provider-contract-check` to validate for `presentation` builds (`google_slides` and `google_docs`). Ignored for `sheets`. Default `false`.
- `provider-contract-params-path` (optional): CSV path for validate contract checks; falls back to `params-path` when unset.
- `dry-run` (optional): Run build with `--dry-run`. Default `false`.
- `threads` (optional): Value passed to `--threads`.
- `requests-per-second` (optional): Value passed to `--rps`.
- `upload-log-artifact` (optional): Upload logs and discovered URLs. Default `true`.
- `artifact-name` (optional): Artifact name. Default `slideflow-build-logs`.

## Outputs

- `presentation-urls`: Comma-separated URLs for `presentation` builds.
- `workbook-urls`: Comma-separated URLs for `sheets` builds.
- `artifact-urls`: Comma-separated URLs for whichever artifact-kind was built.
- `doctor-result-json`: JSON summary emitted by doctor command (`slideflow doctor` or `slideflow sheets doctor`).
- `validate-result-json`: JSON summary emitted by validate command (`slideflow validate` or `slideflow sheets validate`).
- `build-result-json`: JSON summary emitted by build command (`slideflow build` or `slideflow sheets build`).

Example downstream usage:

```yaml
jobs:
  build:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets: inherit
    with:
      config-file: config/report.yml

  notify:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - run: echo "Artifact URLs: ${{ needs.build.outputs['artifact-urls'] }}"
      - run: echo '${{ needs.build.outputs["build-result-json"] }}' > build-result.json
```

## Secrets and Environment

- The reusable workflow maps these optional secrets into runtime environment variables:
- `GOOGLE_SLIDEFLOW_CREDENTIALS`
- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`
- `DBT_GIT_TOKEN` (optional; used when `dbt` or `databricks_dbt` `package_url` includes `$DBT_GIT_TOKEN`)
- `DBT_ACCESS_TOKEN` (optional; if omitted, reusable workflow falls back to `DBT_GIT_TOKEN`)
- `DBT_ENV_SECRET_GIT_CREDENTIAL` (optional; if omitted, reusable workflow falls back to `DBT_ACCESS_TOKEN`, then `DBT_GIT_TOKEN`)
- `BIGQUERY_PROJECT` (optional; project-id fallback for `warehouse.type: bigquery`)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` (optional; creates `GOOGLE_APPLICATION_CREDENTIALS` file during workflow run)
- Callers can either pass those secrets explicitly or use `secrets: inherit` if the same names exist in the caller repository/org.
- Your Slideflow config can continue to reference environment variables as usual.
- For `google_slides` and `google_docs` builds, ensure credentials/folder IDs used by your config are available in the caller workflow environment.
- `google_docs` provider can use `GOOGLE_SLIDEFLOW_CREDENTIALS` in this workflow (or `provider.config.credentials`).
- Prefer pinning reusable workflow references to a commit SHA in production.

If your caller repo stores Google Docs credentials under `GOOGLE_DOCS_CREDENTIALS`,
map it into the reusable workflow's expected secret name:

```yaml
jobs:
  build:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets:
      GOOGLE_SLIDEFLOW_CREDENTIALS: ${{ secrets.GOOGLE_DOCS_CREDENTIALS }}
    with:
      config-file: config/google-docs-report.yml
```

Example `dbt` source for a private dbt repo:

```yaml
data_source:
  type: dbt
  model_alias: revenue_monthly
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/private-dbt-project.git
    project_dir: /tmp/dbt_project
  warehouse:
    type: databricks
```

BigQuery variant:

```yaml
data_source:
  type: dbt
  model_alias: revenue_monthly
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/private-dbt-project.git
    project_dir: /tmp/dbt_project
  warehouse:
    type: bigquery
    project_id: my-gcp-project
    location: US
```

If your dbt dependencies use `env_var('DBT_ENV_SECRET_GIT_CREDENTIAL')`, pass `DBT_ENV_SECRET_GIT_CREDENTIAL` as an optional secret (or rely on fallback to `DBT_ACCESS_TOKEN` / `DBT_GIT_TOKEN`).

For deployment patterns beyond GitHub Actions, see [Deployments](deployments.md).
