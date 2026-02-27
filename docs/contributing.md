# Contributing

SlideFlow expects contribution changes to be tested and documented in the same PR.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ai]"
```

## Required local gates

```bash
python -m pip check
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
python -m pytest -q
```

Optional marker suites:

```bash
python -m pytest -q -m integration
python -m pytest -q -m e2e
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
- When changing constraints, run `python -m pip check` and the relevant test
  suites before opening a PR.

## Additional references

- Root contributing guide: [`CONTRIBUTING.md`](https://github.com/joe-broadhead/slideflow/blob/master/CONTRIBUTING.md)
- Testing details: [Testing](testing.md)
- Compatibility rules: [Compatibility Policy](compatibility-policy.md)
- Release steps: [Release Process](release-process.md)
