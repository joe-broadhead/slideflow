# Troubleshooting

## Validation fails

Run with explicit registries:

```bash
slideflow validate config.yml --registry registry.py
```

Common causes:

- Missing/invalid provider config
- Invalid replacement or chart schema
- Missing function in `function_registry`

## Build fails before rendering

Common causes:

- Credentials not present (`GOOGLE_SLIDEFLOW_CREDENTIALS` or provider credentials)
- Template or slide IDs are invalid
- Data source query/file path is invalid

## Charts fail to render

Common causes:

- Data source returns empty/invalid schema for chart traces
- Chart config references unknown columns
- Plotly/kaleido environment issues

## dbt source fails

Common causes:

- Missing DBT/Databricks dependencies
- Git auth token not configured in environment variable
- DBT profile/target mismatch

## AI replacement fails

Common causes:

- Missing API key or service account auth
- Provider/model mismatch
- Rate limiting from upstream APIs

## CI failures

- `scripts/ci/check_version_consistency.py` failed:
  - Ensure `pyproject.toml` version equals `slideflow/__init__.py`.
- Release branch failed:
  - Branch must match `release/vX.Y.Z`.
  - Version in branch must match project version.
