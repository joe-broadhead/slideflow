# Quickstart

This guide runs the checked-in sample in `docs/quickstart/` end-to-end.

## 1. Prepare sample config

Open `docs/quickstart/config.yml` and set:

- `provider.config.template_id`
- `provider.config.credentials` (or set `GOOGLE_SLIDEFLOW_CREDENTIALS`)
- slide IDs under `presentation.slides[*].id`

## 2. Validate configuration

```bash
slideflow validate docs/quickstart/config.yml --registry docs/quickstart/registry.py
```

Validation checks YAML structure, provider config, chart/replacement wiring, and registry resolution.

## 3. Build a presentation

```bash
slideflow build docs/quickstart/config.yml --registry docs/quickstart/registry.py
```

Expected outcome:

- A new presentation is copied from your template
- Slide 1 gets `{{MONTH}}` replacement and a bar chart from `docs/quickstart/data.csv`
- Slide 2 gets a template chart from `docs/quickstart/bar_chart.yml`

## 4. Batch mode (multi-deck)

Create `variants.csv`:

```csv
MONTH,REGION
January,NA
January,EMEA
```

Run batch build:

```bash
slideflow build docs/quickstart/config.yml \
  --registry docs/quickstart/registry.py \
  --params-path variants.csv
```

Rules:

- CSV headers map to `{param}` placeholders in YAML
- Empty CSV rows are rejected at runtime
- Use `--dry-run` to validate all variants without building

## 5. Control concurrency and rate limits

```bash
slideflow build docs/quickstart/config.yml \
  --registry docs/quickstart/registry.py \
  --threads 2 \
  --rps 1.0
```

Use conservative `--threads` and `--rps` when Google API quotas are tight.

## 6. Troubleshoot fast

If anything fails:

- `slideflow validate ...` first
- verify template and slide IDs
- verify credentials source
- check [Troubleshooting](troubleshooting.md)
