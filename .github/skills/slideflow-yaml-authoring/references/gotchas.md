# Slideflow YAML Authoring Gotchas

## 1) Token syntax and substitution

- `{param}` is runtime substitution and resolved before model parsing.
- `{{PLACEHOLDER}}` is a provider placeholder token and intentionally preserved.
- Unresolved `{param}` may survive if params are missing; verify params CSV headers.

## 2) Provider-specific contract checks

- `slideflow validate --provider-contract-check` supports `google_slides` and `google_docs`.
- For `google_sheets`, run `slideflow sheets doctor --strict` and `slideflow sheets validate`.

## 3) dbt connector shape

- Prefer `type: dbt` + `dbt:` + `warehouse:` for new configs.
- Keep `databricks_dbt` only for legacy compatibility or controlled migration phases.

## 4) Databricks auth split

- Warehouse execution uses:
  - `DATABRICKS_HOST`
  - `DATABRICKS_HTTP_PATH`
  - `DATABRICKS_ACCESS_TOKEN`
- Databricks AI provider uses:
  - `DATABRICKS_TOKEN`

## 5) Databricks AI base URL

- Use `https://<workspace-host>/serving-endpoints` as `provider_args.base_url`.
- Do not set `/invocations` in `base_url`.

## 6) Google credentials

- Google credentials resolve from config credentials first, then environment.
- Value may be a JSON file path or raw JSON string, based on provider support.

## 7) Google Docs chart placement

- `google_docs` ignores `x`, `y`, and alignment placement semantics for charts.
- Keep doc layout deterministic with explicit section markers and ordering.

## 8) Sheets concurrency

- `slideflow sheets build --threads N` is bounded by tab count.
- If `threads > tab_count`, effective workers drop to `tab_count`.

## 9) Batch params CSV pitfalls

- Empty params CSV fails runtime.
- Pandas coercion can convert blank strings to null-like values.
- Quote/normalize values when strict string behavior is required.

