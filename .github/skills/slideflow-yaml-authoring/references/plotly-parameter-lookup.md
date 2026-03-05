# Plotly Parameter Lookup (Slideflow Mapping)

## Mapping shape

- Trace-level Plotly params go in `traces[]`.
- Layout-level Plotly params go in `layout_config`.
- Data columns use `$column_name` references when sourced from a data source.
- Use `plotly_go` when direct Plotly Graph Objects control is needed.

## Deterministic lookup workflow

1. Start from a built-in chart template when possible.
2. Switch to `plotly_go` when template parameters are insufficient.
3. Choose trace classes (`bar`, `scatter`, `pie`, `table`, etc.).
4. Inspect `references/plotly-reference-index.json` for valid properties.
5. Put trace properties in each `traces[]` entry.
6. Put chart-level layout options in `layout_config`.
7. Keep Slideflow placement fields (`x`, `y`, `width`, `height`) at chart root.
8. Run `slideflow validate` then `slideflow build --dry-run` (or provider-specific build flow).

## Common checkpoints

- Do not put layout fields inside trace objects.
- Do not put Slideflow placement fields inside `layout_config`.
- Preserve Plotly template strings like `$%{y:,.0f}` exactly.

