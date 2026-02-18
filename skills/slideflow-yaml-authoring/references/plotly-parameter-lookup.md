# Plotly Parameter Lookup (SlideFlow Mapping)

## Mapping shape

- Trace-level Plotly params go in `traces[]`.
- Layout-level Plotly params go in `layout_config`.
- Data columns should use `$column_name` references when sourced from connectors.

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

## Strategy

1. Start from a built-in template when possible.
2. If required params are not enough, switch to `plotly_go`.
3. Use `custom` only for non-Plotly/non-standard rendering paths.
