# Cookbooks

## 1. Basic KPI deck from CSV

Use when you need a fast deck with a few headline metrics.

### Config pattern

```yaml
provider:
  type: "google_slides"
  config:
    template_id: "<template-id>"

presentation:
  name: "Weekly KPI Report"
  slides:
    - id: "<slide-id-1>"
      replacements:
        - type: "text"
          config:
            placeholder: "{{WEEK}}"
            replacement: "Week 07"
        - type: "text"
          config:
            placeholder: "{{TOTAL_REVENUE}}"
            data_source:
              type: "csv"
              name: "kpi"
              file_path: "./data/kpi.csv"
            value_fn: "get_first_value"
            value_fn_args:
              column: "revenue"
```

### Command

```bash
slideflow validate config.yml --registry registry.py
slideflow build config.yml --registry registry.py
```

## 2. Reusable chart templates with built-ins

Use when your team needs consistent visuals across many decks.

### Pattern

1. Define reusable YAML chart templates in `templates/`.
2. Use `type: template` charts with `template_config` values.
3. Keep styling in templates, business logic in config/data.

```yaml
presentation:
  name: "Template Driven Deck"
  slides:
    - id: "<slide-id>"
      charts:
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

## 3. Fully custom charts + bulk generation

Use when each audience segment needs a tailored deck.

### Pattern

- Create custom chart and formatter functions in `registry.py`
- Use batch params CSV for segment variants
- Run with controlled concurrency and rate limit

```yaml
registry:
  - "./registry.py"

presentation:
  name: "Q{quarter} {region} Review"
  slides:
    - id: "<slide-id>"
      charts:
        - type: "custom"
          config:
            chart_fn: "build_segment_chart"
            data_source:
              type: "databricks"
              name: "segment_sales"
              query: "SELECT * FROM mart.sales WHERE region = '{region}'"
            chart_config:
              quarter: "{quarter}"
```

`variants.csv`:

```csv
quarter,region
Q1,NA
Q1,EMEA
Q1,APAC
```

Command:

```bash
slideflow build config.yml --params-path variants.csv --threads 2 --rps 0.8
```

## Practical tips

- Use `--dry-run` before high-volume runs.
- Keep one shared base registry and add team-specific registries as needed.
- Start with CSV-based fixtures for deterministic testing before moving to live connectors.
