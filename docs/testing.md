# Testing

## Objectives

- Prevent regressions for existing users.
- Validate new behavior before merge/release.
- Keep local feedback loops fast.

## Test layers

1. Unit tests (`tests/`)
   - CLI command behavior
   - config/registry utilities
   - chart/template/replacement behavior
2. Integration tests (`@pytest.mark.integration`)
   - cross-module workflows with controlled fixtures/mocks
3. End-to-end tests (`@pytest.mark.e2e`)
   - full `validate -> build` paths on representative configs
4. Live Google Slides tests (`@pytest.mark.live_google`, `tests/live_tests/`)
   - creates real template presentations via Google API
   - copies template into a new deck during render
   - inserts real charts across full coverage:
     - all built-in template charts
     - direct `plotly_go` charts
     - `custom` chart functions from registry
   - verifies live replacements and function-driven behavior:
     - static text replacement
     - dynamic `value_fn` replacement
     - `ai_text` replacement via deterministic provider function
     - table replacement placeholders
   - verifies image elements and placeholder replacement in rendered slides
   - trashes created files on teardown

## Local commands

```bash
source .venv/bin/activate
python -m pip check
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
pytest -q
pytest -q --cov=slideflow --cov-report=term --cov-report=xml
```

Run only integration or e2e groups:

```bash
pytest -q -m integration
pytest -q -m e2e
```

Mirror CI marker split locally:

```bash
pytest -q -m "not integration and not e2e" --cov=slideflow --cov-report=term --cov-report=xml --cov-fail-under=80
pytest -q -m integration
pytest -q -m e2e
```

Run live template + chart rendering tests locally:

```bash
export SLIDEFLOW_RUN_LIVE=1
export GOOGLE_SLIDEFLOW_CREDENTIALS=/absolute/path/to/service-account.json
export SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID=<drive-folder-id>
# optional override for chart image uploads:
export SLIDEFLOW_LIVE_DRIVE_FOLDER_ID=<drive-folder-id>
# optional template to copy before test mutations:
export SLIDEFLOW_LIVE_TEMPLATE_ID=<google-slides-template-id>
# optional comma-separated emails to share rendered deck with:
export SLIDEFLOW_LIVE_SHARE_EMAIL=<you@example.com>
# optional permission role for shared deck (reader|writer|commenter):
export SLIDEFLOW_LIVE_SHARE_ROLE=reader
# optional retention toggle; defaults to 1 when sharing is enabled:
export SLIDEFLOW_LIVE_KEEP_ARTIFACTS=1

pytest -q tests/live_tests -m live_google
```

When `SLIDEFLOW_LIVE_SHARE_EMAIL` is set, the rendered presentation is shared using the
service account and the test prints the deck URL. Artifacts are retained by default in
that mode so you can validate the slides visually.

## CI quality gates

- CI enforces version consistency checks.
- CI enforces dependency consistency via `pip check`.
- CI enforces coverage floor (`--cov-fail-under=80`) on unit tests (`not integration and not e2e`).
- CI runs dedicated integration and e2e marker suites in separate steps.
- Distribution artifacts are built for every CI run.
- Live Google Slides tests run in a separate workflow (`Live Google Slides`) so PR CI remains deterministic.

## Orchestrated runtime note

- Chart image export runs through headless Kaleido.
- For Cloud Run/Databricks/self-hosted runners, ensure a Chrome/Chromium binary is available in the runtime image.
- On macOS local runs, if desktop Chrome still steals focus, set `CHROME_PATH`
  or `GOOGLE_CHROME_BIN` to a dedicated Chromium/Chrome-for-Testing binary
  instead of `/Applications/Google Chrome.app/...`.

## Compatibility matrix

Compatibility tests assert support remains in place for:

- CLI commands/options (`slideflow build`, `slideflow validate`)
- connectors (`csv`, `json`, `databricks`, `databricks_dbt`)
- replacements (`text`, `table`, `ai_text`)
- charts (`plotly_go`, `custom`, `template`)
- template/registry loading paths

## Contribution expectations

- Every bug fix should include a regression test.
- Every behavior change should update docs and tests in the same PR.
- Release branches should not introduce untested logic.
