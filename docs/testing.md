# Testing Strategy

## Goals

- Protect existing users from regressions.
- Validate new behavior before release.
- Keep fast feedback loops for contributors.

## Test layers

1. Unit tests (`tests/`)
- Validate isolated behavior in CLI, replacements, rendering, connectors, and providers.

2. Integration tests (`@pytest.mark.integration`)
- Validate cross-module behavior and external integrations using controlled fixtures/mocks.

3. End-to-end tests (`@pytest.mark.e2e`)
- Validate full `validate -> build` workflows with representative configs.

## Local commands

```bash
python -m pytest -q
python -m pytest -q --cov=slideflow --cov-report=term
```

## CI policy

- CI must pass on pull requests and protected branches.
- Coverage floor is currently set to a baseline gate and should be ratcheted up over time.
- New features should ship with tests covering expected behavior and edge cases.

## Compatibility focus

Backward compatibility tests should lock in:

- CLI command behavior (`build`, `validate`)
- Config loading and schema validation
- Release-critical provider flows
