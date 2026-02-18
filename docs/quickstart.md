# Quickstart

This quickstart runs the checked-in sample in `docs/quickstart/`.

## 1. Update sample config

Open `docs/quickstart/config.yml` and set:

- `provider.config.template_id`
- `provider.config.credentials`
- slide IDs under `presentation.slides[*].id`

## 2. Validate configuration

```bash
slideflow validate docs/quickstart/config.yml --registry docs/quickstart/registry.py
```

If validation passes, your config, template references, and provider config are structurally valid.

## 3. Build presentation

```bash
slideflow build docs/quickstart/config.yml --registry docs/quickstart/registry.py
```

Expected result:

- A new presentation is created from your template.
- Slide 1 gets `{{MONTH}}` replacement plus bar chart from CSV.
- Slide 2 gets a template chart from `docs/quickstart/bar_chart.yml`.

## 4. Batch mode (optional)

Use `--params-path` to generate multiple variants from one config:

```bash
slideflow build docs/quickstart/config.yml \
  --registry docs/quickstart/registry.py \
  --params-path variants.csv
```

`variants.csv` headers map to `{param}` placeholders used in config.

## 5. Troubleshooting

If build fails, check [Troubleshooting](troubleshooting.md).
