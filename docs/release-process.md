# Release Process

## Branch convention

Release branches must follow:

- `release/vX.Y.Z`

Example:

- `release/v0.0.2`

## Automated release flow

On push to a `release/vX.Y.Z` branch, the `Release` workflow:

1. validates branch naming
2. validates project version consistency
3. runs release test suite + coverage gate
4. builds wheel and source distributions
5. creates and pushes Git tag `vX.Y.Z`
6. creates GitHub release with artifacts
7. publishes package to PyPI (OIDC trusted publishing)

## Version consistency contract

These must match:

- `pyproject.toml` -> `[project].version`
- `slideflow/__init__.py` -> `__version__`
- release branch suffix -> `release/vX.Y.Z`

## Pre-release checklist

1. Ensure tests pass locally.
2. Ensure docs are updated and build cleanly:

```bash
source .venv/bin/activate
pytest -q
mkdocs build --strict
```

3. Bump versions in `pyproject.toml` and `slideflow/__init__.py`.
4. Create release branch `release/vX.Y.Z`.
5. Push and monitor `CI`, `Docs`, and `Release` workflows.

## PyPI trusted publishing setup

1. Create PyPI project (or use existing).
2. Add trusted publisher for this GitHub repo/workflow.
3. Configure GitHub environment `pypi` with any required reviewers.
4. Keep `id-token: write` enabled in release workflow permissions.

## Rollback guidance

If release publish fails after tag creation:

1. fix issue in a new commit on release branch
2. re-run workflow (or push follow-up commit)
3. if needed, delete bad tag and recreate only when corrected artifacts are ready
