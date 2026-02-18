# Troubleshooting

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

- missing Google credentials (`provider.config.credentials` or `GOOGLE_SLIDEFLOW_CREDENTIALS`)
- invalid template ID or slide IDs
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
- invalid `package_url` or missing token env var used in URL
- profile/target mismatch during dbt compile

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
