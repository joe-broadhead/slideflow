# Creating Data-Driven Charts

Charts are a core feature of SlideFlow, allowing you to visualize your data directly on your slides. You can create everything from simple bar charts to complex, multi-trace visualizations using Plotly.

## Core Concepts

All charts are defined within the `charts` list of a slide in your `config.yml`. Each chart has a `type` and a `config` block.

```yaml
- type: "chart_type"
  config:
    # ... configuration for the chart
```

## Types of Charts

SlideFlow supports three types of charts:

### 1. Plotly Graph Objects (`plotly_go`)

This is the most powerful and flexible way to create charts. It gives you access to the full power of the Plotly Graph Objects library. You define your chart by providing a list of `traces` and an optional `layout_config`.

**Example:**

```yaml
- type: "plotly_go"
  config:
    title: "Monthly Revenue"
    data_source:
      type: "csv"
      name: "sales_data"
      file_path: "data/sales.csv"
    traces:
      - type: "bar"
        x: "$month"
        y: "$revenue"
    layout_config:
      xaxis:
        title: "Month"
      yaxis:
        title: "Revenue (USD)"
```

In this example, `$month` and `$revenue` are column references that will be replaced with the actual data from the `sales_data` source.

### 2. Template Chart (`template`)

This chart type allows you to use a reusable YAML template to define your chart. This is a great way to maintain a consistent style across your presentations. See the [Templating](templating.md) guide for more details.

**Example:**

```yaml
- type: "template"
  config:
    title: "Monthly Active Users"
    template_name: "bar_chart"
    data_source:
      type: "csv"
      name: "mau_data"
      file_path: "data/mau.csv"
    template_config:
      title: "Monthly Active Users"
      x_column: "month"
      y_column: "mau"
      y_title: "Active Users"
```

### 3. Custom Chart (`custom`)

For cases where you need complete control over the chart generation logic, you can use a custom Python function. You provide the function name and any additional configuration.

**Example:**

```yaml
- type: "custom"
  config:
    title: "My Custom Chart"
    chart_fn: "create_my_special_chart"
    data_source:
      type: "csv"
      name: "custom_data"
      file_path: "data/custom.csv"
    chart_config:
      # ... additional config for your function
```

## Positioning and Sizing

SlideFlow provides a flexible system for positioning and sizing your charts on the slide.

-   `x`, `y`, `width`, `height`: These properties control the position and size of the chart. They can be numbers or string expressions (e.g., `"400 + 50"`).
-   `dimensions_format`: This specifies the units for the `x`, `y`, `width`, and `height` properties. It can be `pt` (points), `emu` (English Metric Units), or `relative` (a ratio of the page size).
-   `alignment_format`: This allows you to align the chart relative to the slide. For example, `center-top` will center the chart horizontally and align it to the top of the slide.
