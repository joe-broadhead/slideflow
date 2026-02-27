# Contributing

Thanks for contributing to SlideFlow.

## Development setup

1. Use Python 3.12+.
2. Create and activate a virtual environment.
3. Install project dependencies from the tracked lockfile.

```bash
uv sync --extra dev --extra ai --locked
source .venv/bin/activate
```

## Local quality gates (run before opening a PR)

```bash
uv pip check
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
python -m pytest -q
```

Docs validation:

```bash
uv sync --extra docs --locked
uv run mkdocs build --strict
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

## Dependency policy

- Runtime dependencies in `pyproject.toml` (`[project.dependencies]`) must have
  an explicit upper bound.
- dbt adapter ranges must stay compatible with `dbt-core` (same supported minor
  train).
- Security-sensitive dependencies must include explicit minimum versions when
  relevant (for example, `gitpython>=3.1.41`).
- `uv.lock` is tracked in git and is required to be up to date.
- If you change dependency constraints in `pyproject.toml`, run `uv lock` and
  commit the resulting `uv.lock` update in the same PR.
- Validate lock freshness before pushing:

```bash
uv lock --check
```

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
