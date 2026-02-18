# Quickstart

This guide gives you a copy-paste runnable sample first, then shows how to switch to real Google Slides deployment.

## 1. Run the smoke sample (no credentials required)

The smoke sample lives in `docs/quickstart/smoke/` and is designed for `--dry-run` validation.

```bash
cd docs/quickstart/smoke
slideflow validate config.yml
slideflow build config.yml --params-path params.csv --dry-run
```

What this verifies:

- YAML schema validity
- registry function resolution (`registry.py`)
- parameter fan-out from CSV (`params.csv`)
- chart/replacement wiring for a local CSV data source

This exact smoke path is used by CI wheel-install validation (`scripts/ci/run_quickstart_smoke.sh`).

## 2. Switch to a real Google Slides build

Use `docs/quickstart/config.yml` for a real build and set:

- `provider.config.template_id`
- `provider.config.credentials` (or set `GOOGLE_SLIDEFLOW_CREDENTIALS`)
- slide IDs under `presentation.slides[*].id`

Then run:

```bash
slideflow validate docs/quickstart/config.yml --registry docs/quickstart/registry.py
slideflow build docs/quickstart/config.yml --registry docs/quickstart/registry.py
```

Expected outcome:

- A new presentation is copied from your template
- Slide 1 gets `{{MONTH}}` replacement and a bar chart from `docs/quickstart/data.csv`
- Slide 2 gets a template chart from the built-in `bar_basic` template

## 3. Batch mode (multi-deck)

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

## 4. Control concurrency and rate limits

```bash
slideflow build docs/quickstart/config.yml \
  --registry docs/quickstart/registry.py \
  --threads 2 \
  --rps 1.0
```

Use conservative `--threads` and `--rps` when Google API quotas are tight.

## 5. Troubleshoot fast

If anything fails:

- `slideflow validate ...` first
- verify template and slide IDs
- verify credentials source
- check [Troubleshooting](troubleshooting.md)

## 6. CI-parity local gate (recommended before PR)

```bash
source .venv/bin/activate
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
pytest -q
bash scripts/ci/run_quickstart_smoke.sh
```
