# Security & Auth

## Credential sources

For Google Slides provider auth, SlideFlow reads credentials from:

1. `provider.config.credentials`
2. `GOOGLE_SLIDEFLOW_CREDENTIALS`

Credential value can be:

- Path to service-account JSON
- Raw JSON payload

Recommended: use environment variables in CI and avoid storing secrets in repo files.

## Required scopes

Google provider uses:

- `https://www.googleapis.com/auth/presentations`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/drive.file`

## Databricks auth

Databricks connectors require:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

## dbt Git access

For dbt package URLs with embedded token variable:

```text
https://$GIT_TOKEN@github.com/org/dbt-project.git
```

Set `GIT_TOKEN` in environment, not in YAML.

## Logging hygiene

- Do not print raw credential payloads.
- Keep logs at `INFO` or lower in production.
- Use `--debug` only for short-lived troubleshooting sessions.

## CI security posture

The repository includes a dedicated `Audit` workflow that runs:

- dependency audit (`pip-audit`)
- static security scan (`bandit`)

Both reports are uploaded as artifacts for triage.

Audit enforcement policy:

- Audit findings are advisory for all events (pull requests, pushes, schedules).
- Findings are surfaced as warnings and uploaded artifacts for triage follow-up.
- Audit workflow is intentionally non-blocking until baseline findings are
  reduced and a blocking threshold policy is adopted.

Action pinning policy:

- GitHub-maintained actions are version-pinned by major (`@vN`) and updated
  intentionally.
- Third-party actions follow the same major-version pinning policy with periodic
  review during release prep.

## PyPI trusted publishing (recommended)

Use OIDC trusted publishing instead of API tokens.

1. In PyPI project settings, add a trusted publisher:
   - Owner: `joe-broadhead`
   - Repository: `slideflow`
   - Workflow: `release.yml`
   - Environment: `pypi`
2. In GitHub repo settings, create environment `pypi`.
3. Add required reviewers for release protection if needed.
4. Keep `id-token: write` enabled in release workflow permissions.

## Hardening checklist

- [ ] Secrets only via environment or secret manager
- [ ] No credentials committed to Git
- [ ] `slideflow validate` enforced in CI before build/release
- [ ] Audit workflow reviewed weekly
- [ ] Release branch protections enabled
