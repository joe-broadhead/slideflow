# Template Catalog

SlideFlow ships a built-in chart template catalog for common business reporting
patterns. These templates are available out of the box with no `template_paths`
configuration.

## Bars

| Template | Purpose | Key parameters |
| --- | --- | --- |
| `bars/bar_basic` | Single-series bar chart | `title`, `x_column`, `y_column` |
| `bars/bar_grouped` | Two-series grouped bars | `title`, `x_column`, `y1_column`, `y2_column` |
| `bars/bar_stacked` | Two-series stacked bars | `title`, `x_column`, `y1_column`, `y2_column` |

## Lines and Areas

| Template | Purpose | Key parameters |
| --- | --- | --- |
| `lines_areas/line_basic` | Single trend line | `title`, `x_column`, `y_column` |
| `lines_areas/line_multi` | Two trend lines | `title`, `x_column`, `y1_column`, `y2_column` |
| `lines_areas/area_stacked` | Stacked area trend | `title`, `x_column`, `y1_column`, `y2_column` |
| `lines_areas/scatter_trend` | Scatter trend view | `title`, `x_column`, `y_column` |

## Composition

| Template | Purpose | Key parameters |
| --- | --- | --- |
| `composition/donut_breakdown` | Donut composition | `title`, `label_column`, `value_column` |
| `composition/funnel_stage` | Stage conversion funnel | `title`, `stage_column`, `value_column` |
| `composition/waterfall_delta` | Contribution waterfall | `title`, `label_column`, `value_column` |
| `composition/heatmap_matrix` | Matrix intensity heatmap | `title`, `x_column`, `y_column`, `z_column` |

## Distribution

| Template | Purpose | Key parameters |
| --- | --- | --- |
| `distribution/histogram_distribution` | Histogram | `title`, `value_column` |
| `distribution/box_distribution` | Box plot | `title`, `group_column`, `value_column` |

## KPI Cards

| Template | Purpose | Key parameters |
| --- | --- | --- |
| `kpi_cards/kpi_card_single` | Single KPI indicator | `title`, `value_column` |
| `kpi_cards/kpi_card_delta` | KPI indicator with delta | `title`, `value_column`, `reference_column` |

## Tables and Combo

| Template | Purpose | Key parameters |
| --- | --- | --- |
| `tables/table_ranked` | Ranked table | `title`, `column_1`, `column_2` |
| `combo/combo_bar_line` | Bar + line dual-axis combo | `title`, `x_column`, `bar_column`, `line_column` |

## Usage example

```yaml
- type: "template"
  config:
    template_name: "bars/bar_basic"
    data_source:
      type: "csv"
      name: "sales"
      file_path: "./data/sales.csv"
    template_config:
      title: "Revenue by Month"
      x_column: "month"
      y_column: "revenue"
```

## Discovery and inspection

```bash
slideflow templates list --details
slideflow templates info bars/bar_basic
```
