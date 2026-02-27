# Contributing

SlideFlow expects contribution changes to be tested and documented in the same PR.

## Local setup

```bash
uv sync --extra dev --extra ai --locked
source .venv/bin/activate
```

## Required local gates

```bash
uv lock --check
uv pip check
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
python -m pytest -q
```

CI runs this baseline across Python 3.12 and 3.13.

Optional marker suites:

```bash
python -m pytest -q -m integration
python -m pytest -q -m e2e
```

Docs validation:

```bash
uv sync --extra docs --locked
uv run mkdocs build --strict
```

## PR checklist

1. Add regression tests for bug fixes.
2. Update docs for behavior/interface changes.
3. Keep compatibility for existing users unless a breaking change is explicitly planned.
4. Update `CHANGELOG.md` for user-visible changes.

## Dependency constraints policy

- Keep runtime dependency constraints bounded (`min` + `max major/minor`) in
  `pyproject.toml`.
- Keep dbt adapter compatibility aligned with the supported `dbt-core` train.
- Add explicit minimum versions for security-sensitive packages when needed.
- `uv.lock` is tracked and must stay current.
- When changing constraints, run `uv lock` and commit updated `uv.lock` in the
  same PR.

## Additional references

- Root contributing guide: [`CONTRIBUTING.md`](https://github.com/joe-broadhead/slideflow/blob/master/CONTRIBUTING.md)
- Testing details: [Testing](testing.md)
- Compatibility rules: [Compatibility Policy](compatibility-policy.md)
- Release steps: [Release Process](release-process.md)
