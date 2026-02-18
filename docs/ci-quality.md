# CI & Quality

## Workflows

- `CI` (`.github/workflows/ci.yml`)
  - installs project + dev deps
  - runs `pip check`
  - runs unit tests with coverage gate
  - builds distribution artifacts
- `Docs` (`.github/workflows/docs.yml`)
  - runs `mkdocs build --strict`
  - deploys to GitHub Pages on `master`/`main`
- `Release` (`.github/workflows/release.yml`)
  - runs on `release/vX.Y.Z`
  - validates branch/version consistency
  - runs tests + build
  - creates tag + GitHub release
  - publishes to PyPI
- `Audit` (`.github/workflows/audit.yml`)
  - runs `pip-audit`
  - runs `bandit`
  - uploads audit reports as artifacts

## Required local checks before PR

```bash
source .venv/bin/activate
pytest -q
mkdocs build --strict
```

## Coverage policy

- CI enforces a minimum coverage floor (`--cov-fail-under=45`)
- Raise this threshold over time; do not lower it without explicit approval

## Branching policy

- Feature/fix work should ship via PR branches (`codex/*`)
- Release automation only runs from `release/vX.Y.Z`

## Release readiness checklist

- [ ] Tests green in CI
- [ ] Docs strict build green
- [ ] Audit workflow reviewed for new findings
- [ ] Version consistency checks passed
- [ ] Migration notes included for behavior changes
