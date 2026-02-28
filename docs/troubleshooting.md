# Troubleshooting

## Start with doctor

Run this first to catch environment/runtime issues before longer builds:

```bash
slideflow doctor --config-file config.yml --registry registry.py --strict --output-json doctor-result.json
```

## Validation fails

Command:

```bash
slideflow validate config.yml --registry registry.py
```

Common causes:

- provider config missing required fields
- unresolved function names in registry
- invalid replacement/chart schema shape

## Build fails before rendering

Common causes:

- missing Google credentials (`provider.config.credentials`, `GOOGLE_DOCS_CREDENTIALS`, or `GOOGLE_SLIDEFLOW_CREDENTIALS`)
- invalid template ID or target IDs (`slide.id` for `google_slides`, section marker ids for `google_docs`)
- unreadable CSV/JSON input path
- query/auth issues for Databricks connectors

## Batch mode fails early

If using `--params-path`:

- ensure file exists and has headers
- ensure it has at least one data row
- ensure placeholders like `{region}` match header names exactly

## Charts fail to render

Common causes:

- trace config references unknown columns
- transformed data is empty after filters
- runtime image backend issues (`kaleido`)

Helpful check:

```bash
slideflow build config.yml --dry-run
```

## dbt connector issues

Common causes:

- missing Databricks auth env vars
- missing BigQuery project/auth settings when using `warehouse.type: bigquery`
- invalid `package_url` or missing token env var used in URL
- profile/target mismatch during dbt compile

Frequent CI symptom:

- `dbt compile failed: Path '/home/runner/.dbt' does not exist`

Frequent dbt model-resolution symptom:

- `Ambiguous dbt model alias '...'`

Fixes:

- set `dbt.profiles_dir` in your `dbt` source config (or `profiles_dir` in legacy `databricks_dbt`), or
- ensure `profiles.yml` exists at the dbt project root in the cloned repo.

For private dbt deps/repo access, ensure token env vars referenced by
`package_url` or `env_var(...)` are present at runtime.

If alias ambiguity occurs, add one of these selectors in your source config:

- `model_unique_id` (most specific)
- `model_package_name`
- `model_selector_name`

For BigQuery DBT execution, ensure at least one project-id source is available:

- `warehouse.project_id`, or
- `BIGQUERY_PROJECT`, or
- `GOOGLE_CLOUD_PROJECT`.

And provide BigQuery auth via one of:

- `warehouse.credentials_path`,
- `warehouse.credentials_json`, or
- Application Default Credentials (`GOOGLE_APPLICATION_CREDENTIALS`, workload identity, etc).

## NumPy binary-compatibility warnings

If you see warnings like:

- `numpy.integer size changed, may indicate binary incompatibility`
- `numpy.floating size changed, may indicate binary incompatibility`

these indicate a local wheel ABI mismatch. Rebuild the environment from
scratch so NumPy/Pandas are installed as a compatible pair:

```bash
rm -rf .venv
uv sync --extra docs --extra dev --extra ai --locked
source .venv/bin/activate
python scripts/ci/check_numpy_binary_compatibility.py
```

Notes:

- CI now runs the same ABI check script to prevent regressions.
- If your org mirrors wheels, ensure both NumPy and Pandas are resolved from
  the same mirror snapshot.

## AI replacement issues

Common causes:

- missing provider credentials/API keys
- invalid provider name/model combination
- upstream rate-limit or provider outage

## CI failures

- version mismatch:
  - align `pyproject.toml` and `slideflow/__init__.py`
- release branch mismatch:
  - branch must match `release/vX.Y.Z`
- docs strict build failure:
  - fix broken links or invalid markdown references
