# Release Process

## Branch convention

Release branches must follow:

- `release/vX.Y.Z`

Example:

- `release/vX.Y.Z`

## Post-release master policy

After a release completes, `master` tracks the latest released version metadata
until the next release branch is prepared. Unreleased work stays under the
`[Unreleased]` changelog section, while `pyproject.toml`,
`slideflow/__init__.py`, `uv.lock`, and the latest released changelog header all
continue to agree on the last published version.

Release tags must remain ancestors of `master` after release completion. If a
tag was created on a side branch, reconcile by merging the tag side back into
`master`; do not move a published tag unless the package has not been published
and the correction is explicitly approved.

## Automated release flow

On push to a `release/vX.Y.Z` branch, the `Release` workflow:

1. validates branch naming
2. blocks publishing on workflow lint, full CI-style tests, optional connector
   tests, docs build, dependency audit, and live Google validation evidence for
   the same commit
3. validates project version consistency
4. builds wheel and source distributions
5. installs built wheel and runs package smoke validation:
   - `twine check`
   - `pip check`
   - CLI entrypoint import/help
   - packaged built-in template discovery and render
   - quickstart `validate` + `build --dry-run`
6. creates and pushes Git tag `vX.Y.Z`
7. publishes package to PyPI (OIDC trusted publishing)
8. creates GitHub release with artifacts

The protected `google-live-validation` environment must define these variables
with successful GitHub Actions run IDs for the current release commit:

- `SLIDEFLOW_LIVE_GOOGLE_SLIDES_RUN_ID`
- `SLIDEFLOW_LIVE_GOOGLE_DOCS_RUN_ID`
- `SLIDEFLOW_LIVE_GOOGLE_SHEETS_RUN_ID`

The release workflow verifies each run through the GitHub API and requires the
run to be completed, successful, from the matching live workflow file, and bound
to the current `GITHUB_SHA`. Configure required reviewers on the environment so
a human verifies the evidence before publishing can continue.

Idempotency behavior:

- If the same version is already published on PyPI, publish is skipped.
- If tag/release already exist on the same artifact-producing commit, those
  steps are skipped.
- If the PyPI version already exists but the matching tag is missing, or if the
  tag points at any commit other than the current workflow commit, the workflow
  fails. Follow-up commits on a release branch must not silently reuse an
  existing package version or tag.

## Version consistency contract

These must match:

- `pyproject.toml` -> `[project].version`
- `slideflow/__init__.py` -> `__version__`
- latest released `CHANGELOG.md` header
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
uv run python scripts/ci/check_numpy_binary_compatibility.py
uvx --from black==26.3.1 black --check slideflow tests scripts
uv run python -m ruff check slideflow tests scripts
uv run python -m mypy slideflow
uv run pytest -q
uv run mkdocs build --strict
```

4. Verify dependency constraints are still within policy:
   - runtime dependencies have explicit upper bounds
   - dbt adapters remain compatible with the supported `dbt-core` range
   - security-sensitive dependency minimums are preserved
   - `uv.lock` is current for the release branch

5. Bump versions in `pyproject.toml` and `slideflow/__init__.py`.
6. Ensure `CHANGELOG.md` has the matching released header.
7. Create release branch `release/vX.Y.Z`.
8. Push and monitor `CI`, `Docs`, and `Release` workflows.
9. After release completion, merge the release result back to `master` and verify
   `git merge-base --is-ancestor vX.Y.Z master`.

## PyPI trusted publishing setup

1. Create PyPI project (or use existing).
2. Add trusted publisher for this GitHub repo/workflow.
3. Configure GitHub environment `pypi` with any required reviewers.
4. Keep `id-token: write` enabled in release workflow permissions.

## Rollback guidance

If release publish fails after tag creation before PyPI publication:

1. fix issue in a new commit on release branch
2. re-run workflow (or push follow-up commit)
3. if explicitly approved, delete the bad tag and recreate only when corrected
   artifacts are ready

If PyPI publication succeeded, do not move the tag. Publish a corrective release
with a new version and document the incident.
