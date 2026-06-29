# Security & Auth

## Credential sources

For Google provider auth, SlideFlow reads credentials from:

1. `provider.config.credentials`
2. Provider-specific env:
   - `GOOGLE_DOCS_CREDENTIALS` (`google_docs`)
   - `GOOGLE_SHEETS_CREDENTIALS` (`google_sheets`)
3. `GOOGLE_SLIDEFLOW_CREDENTIALS` (shared fallback)
4. `GOOGLE_APPLICATION_CREDENTIALS` (ADC file path)
5. Application Default Credentials from the runtime environment

Credential value can be:

- Path to service-account JSON
- Path to external-account / Workload Identity Federation JSON from trusted env/ADC sources
- Raw JSON payload from trusted env sources
- Runtime ADC credentials, when no explicit credential source is configured

`provider.config.credentials` accepts service-account JSON only. External-account
/ Workload Identity Federation JSON is active credential configuration, so keep
it in trusted environment variables, `GOOGLE_APPLICATION_CREDENTIALS`, or
runtime ADC rather than repository YAML.

Recommended: use environment variables in CI and avoid storing secrets in repo
files. If you use raw JSON, inject it through a secret manager or GitHub
Secrets-backed environment variable; do not paste it into checked-in YAML.
For keyless CI/CD, prefer Workload Identity Federation through
`GOOGLE_APPLICATION_CREDENTIALS` or runtime ADC over long-lived key JSON.

## Keyless CI/CD with Workload Identity Federation

In GitHub Actions, use OIDC to obtain short-lived Google credentials and let
SlideFlow discover them through ADC:

```yaml
permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: "projects/<project-number>/locations/global/workloadIdentityPools/<pool-id>/providers/<provider-id>"
          service_account: "slideflow-runtime@<project-id>.iam.gserviceaccount.com"
          create_credentials_file: true

      - run: slideflow build config.yml
```

The auth action exports `GOOGLE_APPLICATION_CREDENTIALS` for the generated
external-account credentials file. The impersonated service account or ADC
identity still needs normal Google Drive ACLs on templates, destination folders,
Shared Drives, and any reused Sheets workbooks.

## Credential hygiene policy

Do:

- Store Google service-account JSON, OAuth client secrets, refresh tokens,
  Databricks tokens, OpenAI/Gemini keys, dbt Git tokens, and BigQuery credential
  JSON in GitHub Secrets, a platform secret manager, or an untracked local file.
- Prefer `provider.config.credentials` as a path to an untracked local file for
  local work, and prefer provider environment variables in CI.
- Keep generated build JSON, doctor output, and live-test artifacts out of
  public issue comments unless they have been reviewed for sensitive IDs.
- Rotate credentials periodically and after any suspected exposure.

Do not:

- Commit `.env` files, `client_secret*.json`, service-account JSON,
  refresh-token exports, private keys, or raw credential JSON in YAML.
- Put long-lived credentials in examples, docs, screenshots, or generated
  artifacts.
- Share generated chart images publicly unless `chart_image_sharing_mode:
  public` is an explicit, reviewed exception.

Local and CI checks:

```bash
uv run python scripts/ci/check_secret_hygiene.py
uv run pre-commit run detect-secrets --all-files
```

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
- `slideflow validate --provider-contract-check` for `powerpoint` reads only
  the configured local `.pptx` template and does not request Google scopes.
- Validation does not fall back to the broader build-provider scopes unless
  `--provider-contract-full-auth-fallback` is passed explicitly.

## Databricks auth

Databricks connectors require:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

## Redshift auth

Redshift connectors support password auth and IAM/serverless auth. Prefer
environment variables or secret-manager injection for all credentials:

- password auth: `REDSHIFT_HOST`, `REDSHIFT_DATABASE`, `REDSHIFT_USER`,
  `REDSHIFT_PASSWORD`
- IAM auth: `REDSHIFT_IAM`, `REDSHIFT_CLUSTER_IDENTIFIER` or
  `REDSHIFT_SERVERLESS_ACCT_ID`/`REDSHIFT_SERVERLESS_WORK_GROUP`,
  `REDSHIFT_REGION`/`AWS_REGION`/`AWS_DEFAULT_REGION`, and AWS identity env vars/profile
- connection controls: `REDSHIFT_SSL`, `REDSHIFT_SSLMODE`, and
  `REDSHIFT_TIMEOUT`

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
- static security scan (`bandit`) for medium/high severity findings

Both reports are uploaded as artifacts for triage.

The main `CI` and `Release` workflows also run pre-commit, which includes:

- `scripts/ci/check_secret_hygiene.py` for SlideFlow-specific credential file
  names and token shapes
- `detect-secrets` for private keys, high-entropy strings, and provider tokens

Repository controls:

- GitHub secret scanning: enabled
- GitHub secret scanning push protection: enabled
- GitHub secret scanning non-provider patterns: disabled
- GitHub secret scanning validity checks: disabled

Keep `check_secret_hygiene.py` and `detect-secrets` as local/CI controls for
credential classes not covered by repository-level secret scanning.

Audit enforcement policy:

- Dependency vulnerabilities are blocking for pull requests, pushes, schedules,
  and manual runs.
- Static Bandit medium/high severity findings are blocking. Low-signal findings
  should be converted into explicit suppressions or code changes before merge.

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

## Secret incident handling

1. Revoke or rotate the exposed credential at the provider first.
2. Remove the secret from the working tree and from generated artifacts.
3. If the secret reached Git history, coordinate history purging and force-push
   only after maintainers approve the repository impact.
4. Open a private advisory or security issue with affected provider, scope,
   exposure window, rotation evidence, and follow-up owner.
5. Re-run local checks, pre-commit, and GitHub secret-scanning alerts; keep the
   issue open until alerts are closed or explicitly dismissed with rationale.

## Hardening checklist

- [ ] Secrets only via environment or secret manager
- [ ] No credentials committed to Git
- [ ] GitHub secret scanning and push protection enabled
- [ ] `scripts/ci/check_secret_hygiene.py` and `detect-secrets` passing
- [ ] Pre-commit hooks installed and passing (`uv run pre-commit run --all-files`)
- [ ] `slideflow validate` enforced in CI before build/release
- [ ] Audit workflow reviewed weekly
- [ ] Release branch protections enabled
