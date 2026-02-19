# Deployments

This guide covers production execution patterns for SlideFlow in:

- GitHub Actions
- Databricks Workflows
- Cloud Run

## Runtime Prerequisites

For all orchestrated environments, ensure:

- Python 3.12+
- SlideFlow package installed (and `ai` extras if using `ai_text` providers)
- Access to required data systems (Drive/Slides/Databricks/Git)
- Correct environment variables and secrets

For chart image rendering, provide a Chrome/Chromium binary available to Kaleido.
Headless environments still need a browser runtime present.

## GitHub Actions

Use the reusable workflow in this repo:

- `/.github/workflows/reusable-slideflow-build.yml`

Caller example:

```yaml
name: Weekly Business Slides

on:
  schedule:
    - cron: "0 13 * * 1"
  workflow_dispatch:

jobs:
  build:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets: inherit
    with:
      config-file: config/weekly_exec_report.yml
      registry-files: registries/base_registry.py
      params-path: config/weekly_variants.csv
      run-doctor: true
      strict-doctor: false
      run-validate: true
      threads: "2"
      requests-per-second: "1.0"
```

Security notes:

- Prefer pinning reusable workflow refs to a commit SHA.
- Treat `secrets: inherit` as privileged; only call trusted workflows.
- Keep secrets out of YAML files.

### Passing machine-readable outputs to downstream jobs

The reusable workflow exposes:

- `presentation-urls`: comma-separated Google Slides URLs
- `build-result-json`: JSON summary from `slideflow build --output-json`
- `validate-result-json`: JSON summary from `slideflow validate --output-json`
- `doctor-result-json`: JSON summary from `slideflow doctor --output-json`

```yaml
jobs:
  build:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@<pinned_sha>
    secrets: inherit
    with:
      config-file: config/report.yml

  notify:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - run: echo "URLs: ${{ needs.build.outputs['presentation-urls'] }}"
      - run: echo '${{ needs.build.outputs["build-result-json"] }}' > build-result.json
      - run: |
          python - <<'PY'
          import json
          data = json.load(open("build-result.json", "r", encoding="utf-8"))
          urls = [row["url"] for row in data.get("results", []) if row.get("url")]
          print("Structured URLs:", urls)
          PY
```

You can pass these outputs into email/Slack/Teams actions or any parser-based automation.

## Databricks Workflows

Typical pattern:

1. Build a Python environment (wheel or container) with SlideFlow and dependencies.
2. Configure environment variables/secrets in the Databricks job/task.
3. Run:

```bash
slideflow doctor --config-file config.yml --registry registry.py
slideflow validate config.yml --registry registry.py --output-json validate-result.json
slideflow build config.yml --registry registry.py --threads 2 --rps 0.8 --output-json build-result.json
```

If using Databricks connectors, set:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_ACCESS_TOKEN`

If using `databricks_dbt`, also ensure Git token env vars used in `package_url` are available.

## Cloud Run

Use a container image that includes:

- SlideFlow dependencies
- Google credentials access path (or injected JSON env)
- Chrome/Chromium runtime for chart rendering

Recommended command sequence:

```bash
slideflow doctor --config-file /app/config.yml --registry /app/registry.py
slideflow validate /app/config.yml --registry /app/registry.py --output-json /tmp/validate-result.json
slideflow build /app/config.yml --registry /app/registry.py --threads 2 --rps 0.8 --output-json /tmp/build-result.json
```

Operational notes:

- Keep temp storage writable for intermediate artifacts.
- Use structured logs for presentation URL extraction and alerting.
- Start with lower concurrency and increase after observing API quotas.

## Production Rollout Checklist

- `slideflow validate` enforced before `slideflow build`
- `slideflow doctor` runs before long render jobs (strict mode in CI if desired)
- Secrets managed by platform secret manager (not committed)
- API quotas/rate limits measured and tuned (`--rps`, `--threads`)
- Failure notifications wired to orchestration platform
- Build logs and JSON summaries retained for debugging/notifications
