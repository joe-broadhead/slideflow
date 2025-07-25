# Dynamic Content with Replacements

Replacements are a powerful feature in SlideFlow that allow you to dynamically insert content into your slides. This content can be simple text, entire tables, or even text generated by an AI model.

## Core Concepts

All replacements are defined within the `replacements` list of a slide in your `config.yml`. Each replacement has a `type` and a `config` block.

```yaml
- type: "replacement_type"
  config:
    # ... configuration for the replacement
```

## Types of Replacements

SlideFlow supports three types of replacements:

### 1. Text Replacement (`text`)

This is the simplest type of replacement. It replaces a placeholder in your slide with a static or dynamic text value.

**Static Example:**

```yaml
- type: "text"
  config:
    placeholder: "{{TITLE}}"
    replacement: "My Awesome Presentation"
```

**Dynamic Example:**

This example fetches a single value from a data source and uses a custom function to format it.

```yaml
- type: "text"
  config:
    placeholder: "{{TOTAL_REVENUE}}"
    data_source:
      type: "csv"
      name: "sales_data"
      file_path: "data/sales.csv"
    value_fn: "get_first_value"
    value_fn_args:
      column: "revenue"
```

### 2. Table Replacement (`table`)

This replacement type allows you to populate a table in your slide from a DataFrame. It works by mapping each cell in the DataFrame to a placeholder in your slide.

The placeholders are in the format `{{PREFIXrow,col}}`, where `PREFIX` is a prefix you define, `row` is the 1-based row index, and `col` is the 1-based column index.

**Example:**

```yaml
- type: "table"
  config:
    prefix: "SALES_DATA_"
    data_source:
      type: "csv"
      name: "sales_data"
      file_path: "data/sales.csv"
```

This would map the value in the first row and first column of your CSV to the placeholder `{{SALES_DATA_1,1}}`, the value in the first row and second column to `{{SALES_DATA_1,2}}`, and so on.

### 3. AI Text Replacement (`ai_text`)

This replacement type uses an AI provider (like OpenAI or Gemini) to generate text based on a prompt. You can also provide a data source to enrich the prompt with your data.

**Example:**

```yaml
- type: "ai_text"
  config:
    placeholder: "{{SUMMARY}}"
    prompt: "Write a short summary of the following sales data:"
    provider: "openai"
    provider_args:
      model: "gpt-4o"
    data_source:
      type: "csv"
      name: "sales_data"
      file_path: "data/sales.csv"
```

When this replacement is processed, SlideFlow will append the data from `sales.csv` to the prompt before sending it to the OpenAI API.

## Data Sources and Transformations

All replacement types can have a `data_source` and a list of `data_transforms`. This allows you to fetch data from any supported source and to clean, reshape, or aggregate it before it's used in your replacement.
