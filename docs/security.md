# Security & Auth

## Credential sources

For Google provider auth, SlideFlow reads credentials from:

1. `provider.config.credentials`
2. Provider-specific env:
   - `GOOGLE_DOCS_CREDENTIALS` (`google_docs`)
   - `GOOGLE_SHEETS_CREDENTIALS` (`google_sheets`)
3. `GOOGLE_SLIDEFLOW_CREDENTIALS` (shared fallback)

Credential value can be:

- Path to service-account JSON
- Raw JSON payload

Recommended: use environment variables in CI and avoid storing secrets in repo files.

## Required scopes

Google Slides provider scopes:

- `https://www.googleapis.com/auth/presentations`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/drive.file`

Google Docs provider scopes:

- `https://www.googleapis.com/auth/documents`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/drive.file`

Google Sheets provider scopes:

- `https://www.googleapis.com/auth/spreadsheets`
- `https://www.googleapis.com/auth/drive`
- `https://www.googleapis.com/auth/drive.file`

Provider contract validation scopes:

- `slideflow validate --provider-contract-check` for `google_slides` uses
  `https://www.googleapis.com/auth/presentations.readonly`
- `slideflow validate --provider-contract-check` for `google_docs` uses
  `https://www.googleapis.com/auth/documents.readonly`
- Validation does not fall back to the broader build-provider scopes unless
  `--provider-contract-full-auth-fallback` is passed explicitly.

## Databricks auth

Databricks connectors require:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

## dbt Git access

For dbt package URLs with embedded token variable:

```text
https://$DBT_GIT_TOKEN@github.com/org/dbt-project.git
```

Set `DBT_GIT_TOKEN` in environment, not in YAML.

With the default `compile: true`, dbt sources clone the configured repository,
run `dbt deps`, and run `dbt compile`; dbt package code and macros may execute
during that phase. Use trusted dbt repositories/packages and least-privilege
CI secrets. Set `compile: false` only for precompiled local projects with
`target/manifest.json` and compiled SQL files already present; that mode does
not clone or invoke dbt.

## Logging hygiene

- Do not print raw credential payloads.
- Keep logs at `INFO` or lower in production.
- Use `--debug` only for short-lived troubleshooting sessions.
- CLI error rendering, machine-readable JSON output, and reusable workflow JSON
  outputs share centralized redaction for common secret fields, authorization
  headers, bearer/basic tokens, URL userinfo, and sensitive URL query
  parameters.
- `slideflow build --output-json` does not emit batch params by default. Workflow
  JSON outputs publish compact summaries instead of full local result JSON.
- Built-in networked providers/connectors include a `Slideflow` client
  identifier where SDK/API support exists, improving service-side auditability.

## Registry execution risk

Registry files are executable Python modules. SlideFlow loads them dynamically
when `--registry` or `registry:` config paths are provided.

- Only load registry files from trusted repositories and trusted contributors.
- Treat registry review as code review (not data review).
- Do not run untrusted registry files in shared CI runners with broad secrets.
- Prefer least-privilege CI secrets for runs that execute registry code.

## CI security posture

The repository includes a dedicated `Audit` workflow that runs:

- dependency audit (`pip-audit`) from a locked environment that includes the
  supported optional connector extras
- static security scan (`bandit`)

Both reports are uploaded as artifacts for triage.

Audit enforcement policy:

- Dependency vulnerabilities are blocking for pull requests, pushes, schedules,
  and manual runs.
- Static Bandit findings remain advisory while existing low-signal findings are
  triaged and converted into explicit suppressions or code changes.

Default-branch dependency alert closure:

- Treat the locked all-extras `pip-audit` result as the branch-side proof that a
  dependency vulnerability is fixed.
- GitHub Dependabot alerts are considered closed only after the patched
  `uv.lock` reaches the default branch and GitHub reports the alert fixed.
- Before merging a security or hardening PR, list the open Dependabot alerts and
  dependency PRs it supersedes, merges, or intentionally leaves open.
- After the merge, re-check open Dependabot alerts and close superseded
  Dependabot PRs with a comment that points at the fixing PR.
- If any alert remains open after the default-branch merge, keep a follow-up
  issue with the alert IDs, affected package, manifest, patched version, and
  remaining action.

Useful checks:

```bash
uv run pip-audit --progress-spinner off
gh api '/repos/OWNER/REPO/dependabot/alerts?state=open' --paginate
gh pr list --author app/dependabot --state open
```

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
- [ ] Pre-commit hooks installed and passing (`uv run pre-commit run --all-files`)
- [ ] `slideflow validate` enforced in CI before build/release
- [ ] Audit workflow reviewed weekly
- [ ] Release branch protections enabled
