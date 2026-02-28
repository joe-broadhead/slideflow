# Deployments

This guide covers production execution patterns for SlideFlow in:

- GitHub Actions
- Databricks Workflows
- Cloud Run

## Runtime Prerequisites

For all orchestrated environments, ensure:

- Python 3.12+
- SlideFlow package installed (and `ai` extras if using `ai_text` providers)
- Access to required data systems (Drive/Slides/Docs/Databricks/Git)
- Correct environment variables and secrets

For chart image rendering, provide a Chrome/Chromium binary available to Kaleido.
Headless environments still need a browser runtime present.

## GitHub Actions

Use the reusable workflow in this repo:

- `/.github/workflows/reusable-slideflow-build.yml`

Caller example:

```yaml
name: Weekly Business Slides

on:
  schedule:
    - cron: "0 13 * * 1"
  workflow_dispatch:

jobs:
  build:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets:
      GOOGLE_SLIDEFLOW_CREDENTIALS: ${{ secrets.GOOGLE_SLIDEFLOW_CREDENTIALS }}
      DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
      DATABRICKS_HTTP_PATH: ${{ secrets.DATABRICKS_HTTP_PATH }}
      DATABRICKS_ACCESS_TOKEN: ${{ secrets.DATABRICKS_ACCESS_TOKEN }}
      DBT_GIT_TOKEN: ${{ secrets.DBT_GIT_TOKEN }} # optional; for private dbt/databricks_dbt repos
      DBT_ACCESS_TOKEN: ${{ secrets.DBT_ACCESS_TOKEN }} # optional; falls back to DBT_GIT_TOKEN in reusable workflow
      DBT_ENV_SECRET_GIT_CREDENTIAL: ${{ secrets.DBT_ENV_SECRET_GIT_CREDENTIAL }} # optional; falls back to DBT_ACCESS_TOKEN, then DBT_GIT_TOKEN
      BIGQUERY_PROJECT: ${{ secrets.BIGQUERY_PROJECT }} # optional; for dbt warehouse.type=bigquery
      GOOGLE_APPLICATION_CREDENTIALS_JSON: ${{ secrets.GOOGLE_APPLICATION_CREDENTIALS_JSON }} # optional; writes ADC file in reusable workflow
    with:
      config-file: config/weekly_exec_report.yml
      registry-files: registries/base_registry.py
      params-path: config/weekly_variants.csv
      run-doctor: true
      strict-doctor: true
      run-validate: true
      run-provider-contract-check: true
      threads: "2"
      requests-per-second: "1.0"
```

Security notes:

- Prefer pinning reusable workflow refs to a commit SHA.
- Treat inherited or explicitly-mapped secrets as privileged; only call trusted workflows.
- Keep secrets out of YAML files.

Supported reusable-workflow secret mappings:

- `GOOGLE_SLIDEFLOW_CREDENTIALS`
- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`
- `DBT_GIT_TOKEN` (optional; used when `dbt` or `databricks_dbt` `package_url` includes `$DBT_GIT_TOKEN`)
- `DBT_ACCESS_TOKEN` (optional; if omitted, reusable workflow falls back to `DBT_GIT_TOKEN`)
- `DBT_ENV_SECRET_GIT_CREDENTIAL` (optional; if omitted, reusable workflow falls back to `DBT_ACCESS_TOKEN`, then `DBT_GIT_TOKEN`)
- `BIGQUERY_PROJECT` (optional; project id fallback for `warehouse.type: bigquery`)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` (optional; service-account JSON used to create `GOOGLE_APPLICATION_CREDENTIALS` file)

For `google_docs` provider runs with the reusable workflow, use `GOOGLE_SLIDEFLOW_CREDENTIALS`
as the credentials secret mapping (or set `provider.config.credentials` directly in config).

If your caller repo secret is named `GOOGLE_DOCS_CREDENTIALS`, map it explicitly:

```yaml
jobs:
  build:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets:
      GOOGLE_SLIDEFLOW_CREDENTIALS: ${{ secrets.GOOGLE_DOCS_CREDENTIALS }}
    with:
      config-file: config/google-docs-report.yml
```

### Passing machine-readable outputs to downstream jobs

The reusable workflow exposes:

- `presentation-urls`: comma-separated build URLs extracted from JSON output (Google Slides or Google Docs)
- `build-result-json`: JSON summary from `slideflow build --output-json`
- `validate-result-json`: JSON summary from `slideflow validate --output-json`
- `doctor-result-json`: JSON summary from `slideflow doctor --output-json`

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
      - run: echo "URLs: ${{ needs.build.outputs['presentation-urls'] }}"
      - run: echo '${{ needs.build.outputs["build-result-json"] }}' > build-result.json
      - run: |
          python - <<'PY'
          import json
          data = json.load(open("build-result.json", "r", encoding="utf-8"))
          urls = [row["url"] for row in data.get("results", []) if row.get("url")]
          print("Structured URLs:", urls)
          PY
```

You can pass these outputs into email/Slack/Teams actions or any parser-based automation.

## Databricks Workflows

Typical pattern:

1. Build a Python environment (wheel or container) with SlideFlow and dependencies.
2. Configure environment variables/secrets in the Databricks job/task.
3. Run:

```bash
slideflow doctor --config-file config.yml --registry registry.py --strict --output-json doctor-result.json
slideflow validate config.yml --registry registry.py --provider-contract-check --params-path variants.csv --output-json validate-result.json
slideflow build config.yml --registry registry.py --threads 2 --rps 0.8 --output-json build-result.json
```

If using Databricks connectors, set:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

If using `dbt` or `databricks_dbt`, also ensure Git token env vars used in `package_url` are available.  
If your dbt packages rely on `env_var('DBT_ENV_SECRET_GIT_CREDENTIAL')`, set `DBT_ENV_SECRET_GIT_CREDENTIAL` (or rely on the reusable-workflow fallback chain).

If using `dbt` with `warehouse.type: bigquery`, also ensure:

- BigQuery runtime dependencies are installed (`pip install "slideflow-presentations[bigquery]"`), and
- project/auth settings are available via config and/or env (`BIGQUERY_PROJECT`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS`).

Private dbt repo example:

```yaml
data_source:
  type: dbt
  model_alias: monthly_revenue_by_region
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/private-dbt-project.git
    project_dir: /tmp/dbt_project
  warehouse:
    type: databricks

# BigQuery variant
data_source:
  type: dbt
  model_alias: monthly_revenue_by_region
  dbt:
    package_url: https://$DBT_GIT_TOKEN@github.com/org/private-dbt-project.git
    project_dir: /tmp/dbt_project
  warehouse:
    type: bigquery
    project_id: my-gcp-project
    location: US
```

## Cloud Run

Use a container image that includes:

- SlideFlow dependencies
- Google credentials access path (or injected JSON env)
- Chrome/Chromium runtime for chart rendering

Recommended command sequence:

```bash
slideflow doctor --config-file /app/config.yml --registry /app/registry.py --strict --output-json /tmp/doctor-result.json
slideflow validate /app/config.yml --registry /app/registry.py --provider-contract-check --params-path /app/variants.csv --output-json /tmp/validate-result.json
slideflow build /app/config.yml --registry /app/registry.py --threads 2 --rps 0.8 --output-json /tmp/build-result.json
```

Operational notes:

- Keep temp storage writable for intermediate artifacts.
- Use structured logs for presentation URL extraction and alerting.
- Start with lower concurrency and increase after observing API quotas.

## Production Rollout Checklist

- `slideflow validate` enforced before `slideflow build`
- `slideflow doctor` runs before long render jobs (`--strict` in CI)
- provider contract checks enabled where template compatibility guarantees matter (`slideflow validate --provider-contract-check`)
  - `google_slides`: slide-id + placeholder checks
  - `google_docs`: section-marker + placeholder checks
- Secrets managed by platform secret manager (not committed)
- API quotas/rate limits measured and tuned (`--rps`, `--threads`)
- Failure notifications wired to orchestration platform
- Build logs and JSON summaries retained for debugging/notifications
