# Data Transforms

Data transforms let you preprocess a DataFrame before it is consumed by a chart or replacement.
They run in-process and are defined as Python functions in your registry.

## Where Transforms Apply

You can add `data_transforms` in:

- chart configs (`plotly_go`, `template`, `custom`)
- replacement configs (`text`, `table`, `ai_text`)

Transforms are applied in order.

## Transform Contract

Each transform item is a dictionary with:

- `transform_fn`: callable that receives a DataFrame first
- `transform_args`: optional keyword args

Function shape:

```python
def my_transform(df, **kwargs):
    # modify / filter / aggregate
    return df
```

The function must return a DataFrame.

## Registry Example

```python
import pandas as pd


def filter_region(df: pd.DataFrame, region: str) -> pd.DataFrame:
    return df[df["region"] == region].copy()


def add_margin(df: pd.DataFrame, revenue_col: str, cost_col: str) -> pd.DataFrame:
    out = df.copy()
    out["margin"] = out[revenue_col] - out[cost_col]
    return out


function_registry = {
    "filter_region": filter_region,
    "add_margin": add_margin,
}
```

## YAML Example

```yaml
charts:
  - type: "plotly_go"
    config:
      title: "Regional Margin"
      data_source:
        type: "csv"
        name: "sales"
        file_path: "./data/sales.csv"
      data_transforms:
        - transform_fn: "filter_region"
          transform_args:
            region: "{region}"
        - transform_fn: "add_margin"
          transform_args:
            revenue_col: "revenue"
            cost_col: "cost"
      traces:
        - type: "bar"
          x: "$month"
          y: "$margin"
```

Notes:

- `{region}` is parameter substitution (batch/loader params).
- Function names are resolved from `function_registry`.
- You may also use YAML function tags (`!func`) where your workflow prefers explicit callable tagging.

## Template Chart Behavior

For `type: template` charts, transform sources are merged:

1. chart-level `config.data_transforms`
2. template-rendered `data_transforms` (if the template emits them)

That means template defaults and per-use overrides can coexist.

## Failure Behavior

If a transform fails:

- SlideFlow raises `DataTransformError` with function name, args, DataFrame shape, and available columns.
- Rendering of the affected chart/replacement fails according to normal error handling.

## Practical Patterns

- Keep transforms pure (input DataFrame -> output DataFrame).
- Use `.copy()` when mutating to avoid side effects.
- Make transforms schema-aware and fail loudly on missing columns.
- Prefer several small transforms over one large transform function.

## Validation Workflow

1. Validate config and function resolution:

```bash
slideflow validate config.yml --registry registry.py
```

2. Run a dry build when introducing new transforms:

```bash
slideflow build config.yml --registry registry.py --dry-run
```
