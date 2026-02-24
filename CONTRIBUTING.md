# Contributing

Thanks for contributing to SlideFlow.

## Development setup

1. Use Python 3.12+.
2. Create and activate a virtual environment.
3. Install project dependencies with dev extras.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ai]"
```

## Local quality gates (run before opening a PR)

```bash
python -m pip check
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
python -m pytest -q
```

Docs validation:

```bash
python -m pip install \
  "mkdocs>=1.6" \
  "mkdocs-material>=9.5" \
  "mkdocs-minify-plugin>=0.8" \
  "pymdown-extensions>=10.0"
python -m mkdocs build --strict
```

Optional marker suites:

```bash
python -m pytest -q -m integration
python -m pytest -q -m e2e
```

Live Google suite (optional, requires credentials):

```bash
python -m pytest -q tests/live_tests -m live_google
```

## Contribution expectations

- Include regression tests for bug fixes.
- Update docs in the same PR when behavior or interfaces change.
- Preserve backward compatibility unless a breaking change is explicitly planned.
- Keep legacy `databricks_dbt` behavior compatible while extending composable `dbt`.

## Pull request checklist

1. Keep changes scoped to one concern.
2. Ensure CI checks pass.
3. Add/update tests for new behavior.
4. Update `CHANGELOG.md` when user-visible behavior changes.
5. Include migration notes if config shape or defaults changed.

## Release and docs references

- Release process: `docs/release-process.md`
- Compatibility policy: `docs/compatibility-policy.md`
- Testing guidance: `docs/testing.md`
