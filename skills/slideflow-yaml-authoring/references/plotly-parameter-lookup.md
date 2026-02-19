# Plotly Parameter Lookup (SlideFlow Mapping)

## Mapping shape

- Trace-level Plotly params go in `traces[]`.
- Layout-level Plotly params go in `layout_config`.
- Data columns should use `$column_name` references when sourced from connectors.
- Use `plotly_go` when you need direct Plotly Graph Objects control.

## Common trace params

- bar: `x`, `y`, `name`, `marker`
- scatter: `x`, `y`, `mode`, `name`, `line`, `marker`
- pie: `labels`, `values`, `hole`, `textinfo`
- funnel: `x`, `y`, `textinfo`
- indicator: `mode`, `value`, `delta`, `title`
- table: `header`, `cells`

## Common layout params

- `title`
- `xaxis`
- `yaxis`
- `legend`
- `margin`
- `template`

## Deterministic lookup workflow

1. Start from a built-in template when possible.
2. If template parameters are insufficient, switch to `plotly_go`.
3. Identify trace class(es) needed (`Bar`, `Scatter`, `Pie`, `Indicator`, etc.).
4. Check `references/plotly-reference-index.json` for parameter names by class.
5. Place trace params in each `traces[]` entry and layout params in `layout_config`.
6. Keep SlideFlow-specific placement fields (`x`, `y`, `width`, `height`) at chart root.
7. Run `slideflow validate config.yml` and `slideflow build config.yml --dry-run`.

## Gotcha checkpoints

- Do not put Plotly layout fields inside a trace object.
- Do not put SlideFlow placement fields inside `layout_config`.
- `$column` resolution requires matching DataFrame columns; use literals for static charts.
- Preserve Plotly template strings like `$%{y:,.0f}` exactly.
