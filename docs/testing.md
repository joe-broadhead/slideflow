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

## CI quality gates

- CI enforces version consistency checks.
- CI enforces dependency consistency via `pip check`.
- CI enforces coverage floor (`--cov-fail-under=80`) on unit tests (`not integration and not e2e`).
- CI runs dedicated integration and e2e marker suites in separate steps.
- Distribution artifacts are built for every CI run.

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
