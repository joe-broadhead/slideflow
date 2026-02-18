# CI & Quality

## Workflows

- `CI` (`.github/workflows/ci.yml`)
  - installs project + dev deps
  - runs `pip check`
  - runs `black --check`, `ruff check`, and `mypy`
  - runs unit tests with coverage gate (`-m "not integration and not e2e"`)
  - runs integration marker tests (`-m integration`)
  - runs e2e marker tests (`-m e2e`)
  - builds wheel/sdist artifacts and verifies distribution identity (`slideflow-presentations`)
  - installs built wheel and runs quickstart smoke validation (`validate` + `build --dry-run`)
- `Docs` (`.github/workflows/docs.yml`)
  - runs `mkdocs build --strict`
  - deploys to GitHub Pages on `master`/`main`
- `Release` (`.github/workflows/release.yml`)
  - runs on `release/vX.Y.Z`
  - validates branch/version consistency
  - runs format/lint/type/test/build checks
  - verifies distribution identity (`slideflow-presentations`)
  - publishes to PyPI first
  - creates tag + GitHub release only after publish succeeds
- `TestPyPI Dry Run` (`.github/workflows/testpypi-dry-run.yml`)
  - runs on `release/vX.Y.Z` pushes and manual dispatch
  - runs format/lint/type/build checks
  - verifies distribution identity (`slideflow-presentations`)
  - builds artifacts + smoke tests installed wheel
  - publishes to TestPyPI using OIDC (`skip-existing`)
- `Audit` (`.github/workflows/audit.yml`)
  - runs `pip-audit`
  - runs `bandit`
  - uploads audit reports as artifacts

## Required local checks before PR

```bash
source .venv/bin/activate
python -m pip check
python -m black --check slideflow tests scripts
python -m ruff check slideflow tests scripts
python -m mypy slideflow
pytest -q
pytest -q -m "not integration and not e2e" --cov=slideflow --cov-report=term --cov-fail-under=75
pytest -q -m integration
pytest -q -m e2e
mkdocs build --strict
```

To run the same smoke validation CI uses:

```bash
bash scripts/ci/run_quickstart_smoke.sh
```

## Coverage policy

- CI enforces a minimum coverage floor (`--cov-fail-under=80`)
- Raise this threshold over time; do not lower it without explicit approval

## Branching policy

- Feature/fix work should ship via PR branches (for example `feature/*`, `fix/*`, `hotfix/*`)
- Release automation only runs from `release/vX.Y.Z`

## Release readiness checklist

- [ ] Tests green in CI
- [ ] Docs strict build green
- [ ] Audit workflow reviewed for new findings
- [ ] Version consistency checks passed
- [ ] Migration notes included for behavior changes
