# Release Process

## Branch convention

Release branches must follow:

- `release/vX.Y.Z`

Example:

- `release/vX.Y.Z`

## Automated release flow

On push to a `release/vX.Y.Z` branch, the `Release` workflow:

1. validates branch naming
2. validates project version consistency
3. validates NumPy/Pandas ABI compatibility
4. runs release test suite + coverage gate
5. builds wheel and source distributions
6. installs built wheel and runs quickstart smoke validation (`validate` + `build --dry-run`)
7. publishes package to PyPI (OIDC trusted publishing)
8. creates and pushes Git tag `vX.Y.Z`
9. creates GitHub release with artifacts

Idempotency behavior:

- If the same version is already published on PyPI, publish is skipped.
- If tag/release already exist, those steps are skipped.
- This keeps reruns green when a release branch receives a follow-up docs/metadata commit.

## Version consistency contract

These must match:

- `pyproject.toml` -> `[project].version`
- `slideflow/__init__.py` -> `__version__`
- release branch suffix -> `release/vX.Y.Z`

PyPI package identity:

- distribution name: `slideflow-presentations`
- import namespace: `slideflow`
- CLI command: `slideflow`

## Pre-release checklist

1. Ensure tests pass locally.
2. Update docs + changelog in the same release prep PR:

- update user-facing docs for new behavior/flags/workflows
- update `CHANGELOG.md` with release notes and known issues

3. Ensure docs build cleanly:

```bash
uv sync --extra docs --extra dev --extra ai --locked
source .venv/bin/activate
uv lock --check
uv pip check
python scripts/ci/check_numpy_binary_compatibility.py
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
pytest -q
uv run mkdocs build --strict
```

4. Verify dependency constraints are still within policy:

- runtime dependencies have explicit upper bounds
- dbt adapters remain compatible with the supported `dbt-core` range
- security-sensitive dependency minimums are preserved
- `uv.lock` is current for the release branch

5. Bump versions in `pyproject.toml` and `slideflow/__init__.py`.
6. Create release branch `release/vX.Y.Z`.
7. Push and monitor `CI`, `Docs`, and `Release` workflows.

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
