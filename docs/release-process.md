# Release Process

## Branch convention

Release branches must follow:

- `release/vX.Y.Z`

Example:

- `release/v0.0.2`

## Automated release flow

On push to a `release/vX.Y.Z` branch, CI will:

1. Validate release branch format.
2. Validate version consistency across metadata.
3. Run the release test suite.
4. Build source and wheel artifacts.
5. Create/push tag `vX.Y.Z`.
6. Create GitHub release with artifacts.
7. Publish to PyPI.

## Required version consistency

The following must match:

- `pyproject.toml` -> `[project].version`
- `slideflow/__init__.py` -> `__version__`
- release branch version (`release/vX.Y.Z`)

## Manual checklist before branching

1. Ensure tests pass locally.
2. Ensure docs are up to date.
3. Bump versions in `pyproject.toml` and `slideflow/__init__.py`.
4. Create branch `release/vX.Y.Z`.
5. Push branch and monitor workflow results.
