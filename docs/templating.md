# Templating

SlideFlow templates let you define reusable chart configurations in YAML and apply
parameterized values per slide.

## Template contract

Each template file must contain:

- `name`
- `description`
- `version`
- `parameters[]`
- `template`

Minimal example:

```yaml
name: "Reusable Bar"
description: "Simple reusable bar chart"
version: "1.0"
parameters:
  - name: "title"
    type: "string"
    required: true
  - name: "x_column"
    type: "string"
    required: true
  - name: "y_column"
    type: "string"
    required: true
template: |
  traces:
    - type: "bar"
      x: "${{ x_column }}"
      y: "${{ y_column }}"
  layout_config:
    title: "{{ title }}"
```

## Using templates in `config.yml`

```yaml
- type: "template"
  config:
    template_name: "bar_basic"
    data_source:
      type: "csv"
      name: "sales"
      file_path: "./data/sales.csv"
    template_config:
      title: "Revenue by Month"
      x_column: "month"
      y_column: "revenue"
```

## Discovery and precedence

Template resolution is deterministic and non-breaking:

1. User-provided `template_paths` (in listed order)
2. Project default `./templates`
3. User default `~/.slideflow/templates`
4. Packaged SlideFlow built-ins (`slideflow/templates`)

If the same template name exists in multiple locations, earlier paths win. This
means local/project templates override packaged built-ins.

## Names and categories

Built-ins are organized in category folders (for example `bars/bar_basic`). You can
reference templates by either:

- Relative path name: `bars/bar_basic`
- Bare template name: `bar_basic` (works when unique)

## Inspect template catalog from CLI

List templates:

```bash
slideflow templates list
slideflow templates list --details
```

Inspect one template:

```bash
slideflow templates info bar_basic
```

## Available Jinja filters

Built-in filters include:

- string helpers: `title_case`, `snake_to_kebab`, `add_prefix`, `add_suffix`
- list helpers: `enumerate_list`, `zip_lists`, `repeat_value`
- conditionals: `if_else`, `default_if_none`, `contains`, `starts_with`, `ends_with`
- formatting helpers: `chart_alignment`, `column_width`, `column_format`
- math helpers: `multiply`, `divide`, `round_number`

For built-in template catalog details, see [Template Catalog](template-catalog.md).
For creating your own templates, see [Template Authoring](template-authoring.md).
