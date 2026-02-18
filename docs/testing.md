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
pytest -q
pytest -q --cov=slideflow --cov-report=term --cov-report=xml
```

Run only integration or e2e groups:

```bash
pytest -q -m integration
pytest -q -m e2e
```

## CI quality gates

- CI enforces version consistency checks.
- CI enforces dependency consistency via `pip check`.
- CI enforces coverage floor (`--cov-fail-under=70`).
- Distribution artifacts are built for every CI run.

## Contribution expectations

- Every bug fix should include a regression test.
- Every behavior change should update docs and tests in the same PR.
- Release branches should not introduce untested logic.
