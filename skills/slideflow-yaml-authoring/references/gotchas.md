# SlideFlow YAML Authoring Gotchas

## 1) Token syntax and substitution

- `{param}` is runtime substitution (`str.format`) and is resolved before model parsing.
- `{{PLACEHOLDER}}` is a presentation placeholder and is intentionally preserved.
- Missing `{param}` keys do not hard-fail substitution; unresolved tokens can survive into runtime.
- When authoring literals that contain braces, confirm they are not accidentally treated as params.

## 2) Template IDs and precedence

- Template IDs come from `slideflow templates list`; prefer full IDs like `bars/bar_basic`.
- Bare names are allowed, but resolution uses first recursive match. If duplicate names exist, behavior can be surprising.
- Runtime precedence is deterministic:
  1. `template_paths` in config (user-specified, highest)
  2. `./templates`
  3. `~/.slideflow/templates`
  4. packaged built-ins
- Use explicit IDs and intentional path ordering for local overrides.

## 3) Registry path and import behavior

- Function names (for transforms, `chart_fn`, `name_fn`, etc.) must exist in a module-level `function_registry`.
- Registry resolution order is:
  1. CLI `--registry`
  2. config `registry` (resolved relative to config file)
  3. `<config_dir>/registry.py` if present
  4. `./registry.py` if present
- If a registry module uses relative imports, keep it in a proper package layout (`__init__.py` present).

## 4) Plotly column references

- In `plotly_go`, scalar strings starting with `$` are treated as column refs, except Plotly template strings like `$%{y:,.0f}`.
- Use `$column[index]` when a scalar value is required (`indicator.value`, `delta.reference`), e.g. `$kpi[0]` or `$kpi[-1]`.
- In list values, column refs must match `^\$([a-zA-Z_]\w*)$`; names with spaces/hyphens will not resolve.
- For static charts (no `data_source`), do not rely on `$column` values; provide literal arrays.

## 5) Batch params CSV pitfalls

- `--params-path` expects at least one row; empty CSV fails.
- CSV values are loaded via pandas and may be type-coerced (e.g., blanks -> `NaN`, ints -> floats).
- Header names must exactly match `{param}` tokens.
- If you need strict strings, quote and normalize values before using them in runtime templates.

## 6) Positioning and dimensions

- `x`, `y`, `width`, `height` default to points (`dimensions_format: pt`).
- Supported formats: `pt`, `emu`, `relative`, `expression`.
- `alignment_format` must be `horizontal-vertical` with:
  - horizontal: `left|center|right`
  - vertical: `top|center|bottom`
- `scale` controls image render density, not slide placement coordinates.

## 7) Credentials and environment contracts

- Google Slides credentials are resolved from `provider.config.credentials` first, then `GOOGLE_SLIDEFLOW_CREDENTIALS`.
- Google credentials value can be a file path or a raw JSON string.
- Databricks connectors expect:
  - `DATABRICKS_HOST`
  - `DATABRICKS_HTTP_PATH`
  - `DATABRICKS_ACCESS_TOKEN`

## 8) DBT + Databricks specifics

- `model_alias` must map to a compiled node alias in `manifest.json`.
- Compile/cache identity includes repo URL, branch, target, vars, profiles path, and profile name.
- Keep DBT variant inputs explicit and stable when expecting deterministic reuse.
