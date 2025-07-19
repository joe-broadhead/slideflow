# Templating

SlideFlow's templating engine allows you to create reusable chart definitions using YAML. This is a powerful feature that can help you to maintain a consistent style across your presentations and to reduce the amount of boilerplate configuration in your `config.yml` files.

## The Concept

A template is a YAML file that defines a chart's structure and appearance. It can have parameters that allow you to customize the chart at build time. For example, you could have a template for a bar chart that allows you to specify the title, the x-axis column, and the y-axis column.

When you use a template in your `config.yml`, you provide values for these parameters. SlideFlow then combines the template with your parameters to generate the final chart configuration.

## Creating a Template

Let's take a look at the `bar_chart.yml` template that we created in the quickstart directory:

```yaml
name: "Reusable Bar Chart"
description: "A standard bar chart with customizable title, x-axis, and y-axis."
version: "1.0"

parameters:
  - name: "title"
    type: "string"
    required: true
    description: "The title of the chart."
  - name: "x_column"
    type: "string"
    required: true
    description: "The name of the column to use for the x-axis."
  - name: "y_column"
    type: "string"
    required: true
    description: "The name of the column to use for the y-axis."
  - name: "x_title"
    type: "string"
    required: false
    default: ""
    description: "The title for the x-axis."
  - name: "y_title"
    type: "string"
    required: false
    default: ""
    description: "The title for the y-axis."

template:
  traces:
    - type: "bar"
      x: "${{ x_column }}"
      y: "${{ y_column }}"
  layout_config:
    title: "{{ title }}"
    xaxis:
      title: "{{ x_title if x_title else x_column|title_case }}"
    yaxis:
      title: "{{ y_title if y_title else y_column|title_case }}"
```

This template defines a bar chart with five parameters: `title`, `x_column`, `y_column`, `x_title`, and `y_title`. The `template` section uses Jinja2 syntax to define the chart's configuration. For example, `{{ title }}` will be replaced with the value of the `title` parameter.

## Using a Template

To use this template in your `config.yml`, you would add a chart with the type `template` and provide the template name and the required parameters:

```yaml
- type: "template"
  config:
    template_name: "bar_chart"
    template_config:
      title: "Monthly Revenue"
      x_column: "month"
      y_column: "revenue"
```

When you build your presentation, SlideFlow will find the `bar_chart.yml` template, combine it with your parameters, and generate a bar chart with the title "Monthly Revenue", the `month` column on the x-axis, and the `revenue` column on the y-axis.

## Template Locations

By default, SlideFlow looks for templates in the following locations:

1.  A `templates` directory in your current working directory (`./templates`)
2.  A global SlideFlow templates directory in your home folder (`~/.slideflow/templates/`)

You can also specify a custom location for your templates by adding a `template_paths` section to your `config.yml`:

```yaml
template_paths:
  - "/path/to/your/templates"
```

## Available Jinja2 Filters

SlideFlow provides a number of built-in Jinja2 filters that you can use in your templates. These filters allow you to transform your data and to create more dynamic and flexible templates.

### String Transformations

-   `title_case`: Converts a string from `snake_case` to `Title Case`.
-   `snake_to_kebab`: Converts a string from `snake_case` to `kebab-case`.
-   `add_prefix`: Adds a prefix to a string (defaults to `$`).
-   `add_suffix`: Adds a suffix to a string.

### List Operations

-   `enumerate_list`: Enumerates a list, returning a list of `(index, value)` tuples.
-   `zip_lists`: Zips multiple lists together.
-   `repeat_value`: Repeats a value a specified number of times.

### Color and Styling

-   `alternating_colors`: Generates alternating colors for a list.
-   `color_reference`: Generates a color column reference (e.g., `$_color_col_0`).
-   `hex_to_rgb`: Converts a hex color code to an RGB string.

### Conditionals

-   `if_else`: A simple ternary operator.
-   `default_if_none`: Returns a default value if a value is `None`.
-   `contains`: Checks if a string contains a substring.
-   `starts_with`: Checks if a string starts with a prefix.
-   `ends_with`: Checks if a string ends with a suffix.

### Chart Helpers

-   `chart_alignment`: Determines the text alignment for a column.
-   `column_width`: Determines the width of a column based on a mapping.
-   `column_format`: Determines the format string for a column based on a mapping.

### Math

-   `multiply`: Multiplies a value by a factor.
-   `divide`: Divides a value by a divisor.
-   `round_number`: Rounds a number to a specified number of digits.
