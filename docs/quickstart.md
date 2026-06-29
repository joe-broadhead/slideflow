# Quickstart

This guide gives you a copy-paste runnable sample first, then shows how to switch to real Google Slides, Google Docs, Google Sheets, or local PowerPoint builds.

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
- Slide 2 gets a template chart from the built-in `bars/bar_basic` template

## 3. Switch to a real Google Docs build

Use a config with `provider.type: google_docs`, then set:

- `provider.config.template_id`
- `provider.config.credentials` (or `GOOGLE_DOCS_CREDENTIALS` / `GOOGLE_SLIDEFLOW_CREDENTIALS`)
- section markers in your template (for example `{{SECTION:intro}}`) that match `presentation.slides[*].id`

Then run:

```bash
slideflow validate path/to/google-docs-config.yml --provider-contract-check
slideflow build path/to/google-docs-config.yml
```

Expected outcome:

- A new document is copied from your template
- Replacements run inside matched section-marker blocks
- Charts are inserted inline in those same sections

## 4. Switch to a real Google Sheets build

Use a config with `provider.type: google_sheets` and a top-level `workbook:` block, then set:

- `provider.config.spreadsheet_id` to reuse an existing spreadsheet, or `provider.config.drive_folder_id` to create a new workbook in a Drive folder
- `provider.config.credentials` (or `GOOGLE_SHEETS_CREDENTIALS` / `GOOGLE_SLIDEFLOW_CREDENTIALS`)
- tab names, write modes, and data sources under `workbook.tabs[]`

Then run:

```bash
slideflow sheets validate path/to/workbook.yml
slideflow sheets doctor path/to/workbook.yml --strict
slideflow sheets build path/to/workbook.yml
```

Expected outcome:

- Replace-mode tabs are cleared and rewritten from the configured start cell
- Append-mode tabs use run-key metadata to avoid duplicate writes
- Optional tab-local AI summaries are written to same-sheet or summary-tab placements

## 5. Switch to a local PowerPoint build

Install the optional extra and use a config with `provider.type: powerpoint`:

```bash
uv sync --extra dev --extra ai --extra powerpoint --locked
```

Set:

- `provider.config.template_path` to a local `.pptx` template
- `provider.config.output_dir` to a writable output directory
- `presentation.slides[*].id` to one-based slide indexes such as `"1"` and `"2"`, or native slide IDs when `slide_id_mode: native`

Then run:

```bash
slideflow validate path/to/powerpoint.yml --provider-contract-check
slideflow build path/to/powerpoint.yml
```

Expected outcome:

- A new `.pptx` is written to `output_dir`
- Replacements run in text boxes and table cells
- Charts are inserted into the configured slide regions

## 6. Batch mode (multi-deck or multi-doc)

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

## 7. Control concurrency and rate limits

```bash
slideflow build docs/quickstart/config.yml \
  --registry docs/quickstart/registry.py \
  --threads 2 \
  --rps 1.0
```

Use conservative `--threads` and `--rps` when Google API quotas are tight.
For workbook pipelines, the same controls are available through `slideflow sheets build`.

## 8. Troubleshoot fast

If anything fails:

- `slideflow validate ...` first
- verify template and slide IDs
- verify workbook tab names and target cells for Sheets builds
- verify local `.pptx` template paths and writable output directories for PowerPoint builds
- verify credentials source
- verify connector credentials for your runtime target
- check [Troubleshooting](troubleshooting.md)

## 9. CI-parity local gate (recommended before PR)

```bash
source .venv/bin/activate
uvx --from black==26.3.1 black --check slideflow tests scripts
uv run python -m ruff check slideflow tests scripts
uv run python -m mypy slideflow
uv run pytest -q
uv run bash scripts/ci/run_quickstart_smoke.sh
```
