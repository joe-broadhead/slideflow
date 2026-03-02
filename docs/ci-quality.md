# CI & Quality

## Workflows

- `CI` (`.github/workflows/ci.yml`)
  - enforces lock freshness with `uv lock --check`
  - installs project + dev deps with locked resolution (`uv sync --extra dev --extra ai --locked`)
  - runs `uv pip check`
  - runs NumPy/Pandas ABI compatibility check (`scripts/ci/check_numpy_binary_compatibility.py`)
  - runs `black --check`, `ruff check`, and `mypy`
  - runs unit tests with coverage gate (`-m "not integration and not e2e"`)
  - runs integration marker tests (`-m integration`)
  - runs e2e marker tests (`-m e2e`)
  - builds wheel/sdist artifacts and verifies distribution identity (`slideflow-presentations`)
  - installs built wheel and runs quickstart smoke validation (`validate` + `build --dry-run`)
- `Docs` (`.github/workflows/docs.yml`)
  - runs `mkdocs build --strict`
  - deploys to GitHub Pages on `master`/`main`
- `Release` (`.github/workflows/release.yml`)
  - runs on `release/vX.Y.Z`
  - validates branch/version consistency
  - validates NumPy/Pandas ABI compatibility
  - runs format/lint/type/test/build checks
  - verifies distribution identity (`slideflow-presentations`)
  - publishes to PyPI first
  - creates tag + GitHub release only after publish succeeds
- `Audit` (`.github/workflows/audit.yml`)
  - runs `pip-audit`
  - runs `bandit`
  - uploads audit reports as artifacts
- `Live Google Slides` (`.github/workflows/live-google-slides.yml`)
  - runs on manual dispatch (`workflow_dispatch`) only
  - executes `pytest -q tests/live_tests -m live_google`
  - uses dedicated secrets/folders to create real template-based presentations
  - validates full feature matrix behavior (all built-in chart templates, direct Plotly charts, custom chart function, AI text, dynamic function replacements)
  - requires secrets: `GOOGLE_SLIDEFLOW_CREDENTIALS`, `SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID`
  - optional secret: `SLIDEFLOW_LIVE_TEMPLATE_ID` (seed template to copy before test mutation)
  - optional secret: `SLIDEFLOW_LIVE_SHARE_EMAIL` (share rendered deck for manual visual verification)
  - workflow pins `SLIDEFLOW_LIVE_KEEP_ARTIFACTS=0` to avoid leaving artifacts in CI runs
- `Live Google Docs` (`.github/workflows/live-google-docs.yml`)
  - runs on manual dispatch (`workflow_dispatch`) only
  - executes `pytest -q tests/live_tests -m live_google_docs`
  - uses dedicated secrets/folders to create real template-based documents
  - validates marker-scoped replacements and inline chart insertion behavior
  - requires secrets: `GOOGLE_DOCS_CREDENTIALS` (or `GOOGLE_SLIDEFLOW_CREDENTIALS` fallback), `SLIDEFLOW_LIVE_DOCUMENT_FOLDER_ID` (or `SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID` fallback)
  - optional secret: `SLIDEFLOW_LIVE_DOC_TEMPLATE_ID` (seed template to copy before test mutation)
  - optional secret: `SLIDEFLOW_LIVE_SHARE_EMAIL` (share rendered doc for manual visual verification)
  - workflow pins `SLIDEFLOW_LIVE_KEEP_ARTIFACTS=0` to avoid leaving artifacts in CI runs
- `Live Google Sheets` (`.github/workflows/live-google-sheets.yml`)
  - runs on manual dispatch (`workflow_dispatch`) only
  - executes `pytest -q tests/live_tests -m live_google_sheets`
  - uses dedicated secrets/folders to create real workbook artifacts
  - validates replace + append idempotency behavior against Google Sheets APIs
  - requires secrets: `GOOGLE_SHEETS_CREDENTIALS` (or `GOOGLE_SLIDEFLOW_CREDENTIALS` fallback), `SLIDEFLOW_LIVE_SHEETS_FOLDER_ID` (or presentation/document folder fallback)
  - optional secret: `SLIDEFLOW_LIVE_SHARE_EMAIL` (share rendered workbook for manual verification)
  - workflow pins `SLIDEFLOW_LIVE_KEEP_ARTIFACTS=0` to avoid leaving artifacts in CI runs

## Required local checks before PR

```bash
uv sync --extra docs --extra dev --extra ai --locked
source .venv/bin/activate
uv lock --check
uv pip check
python scripts/ci/check_numpy_binary_compatibility.py
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
pytest -q
pytest -q -m "not integration and not e2e" --cov=slideflow --cov-branch --cov-report=term --cov-fail-under=82
pytest -q -m integration
pytest -q -m e2e
uv run mkdocs build --strict
```

To run the same smoke validation CI uses:

```bash
bash scripts/ci/run_quickstart_smoke.sh
```

## Coverage policy

- CI enforces branch-aware coverage (`--cov-branch`) with minimum floor `82`
- Staged threshold plan:
  - current floor: `82`
  - next target floor: `85` after planned test-hardening changes
- Do not lower thresholds without explicit maintainer approval

## Branching policy

- Feature/fix work should ship via PR branches (for example `feature/*`, `fix/*`, `hotfix/*`)
- Release automation only runs from `release/vX.Y.Z`

## Release readiness checklist

- [ ] Tests green in CI
- [ ] Docs strict build green
- [ ] Audit workflow reviewed for new findings
- [ ] Version consistency checks passed
- [ ] Migration notes included for behavior changes
