# Automation

Use Slideflow's reusable workflow to run scheduled deck builds for business teams.

## Reusable Workflow

Workflow path:

`/.github/workflows/reusable-slideflow-build.yml`

You can call it from another repo with:

```yaml
uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@master
```

## Scheduled Caller Example

```yaml
name: Weekly Business Slides

on:
  schedule:
    - cron: "0 13 * * 1" # Mondays at 13:00 UTC
  workflow_dispatch:

jobs:
  weekly-slides:
    uses: joe-broadhead/slideflow/.github/workflows/reusable-slideflow-build.yml@master
    secrets: inherit
    with:
      config-file: config/weekly_exec_report.yml
      registry-files: |
        registries/base_registry.py
        registries/team_registry.py
      params-path: config/weekly_variants.csv
      run-validate: true
      threads: "2"
      requests-per-second: "1.0"
      upload-log-artifact: true
      artifact-name: weekly-slideflow-logs
```

## Inputs

- `config-file` (required): Path to Slideflow YAML config.
- `registry-files` (optional): Comma/newline-separated registry file paths.
- `params-path` (optional): CSV file for multi-variant builds.
- `working-directory` (optional): Command working directory. Default `.`.
- `python-version` (optional): Python version. Default `3.12`.
- `slideflow-package-spec` (optional): Package to install. Default `slideflow-presentations`.
- `extra-pip-packages` (optional): Newline-separated additional packages.
- `run-pip-check` (optional): Run `pip check`. Default `true`.
- `run-validate` (optional): Run `slideflow validate` before build. Default `true`.
- `dry-run` (optional): Run build with `--dry-run`. Default `false`.
- `threads` (optional): Value passed to `--threads`.
- `requests-per-second` (optional): Value passed to `--rps`.
- `upload-log-artifact` (optional): Upload logs and discovered URLs. Default `true`.
- `artifact-name` (optional): Artifact name. Default `slideflow-build-logs`.

## Outputs

- `presentation-urls`: Comma-separated Google Slides URLs found in logs.

## Secrets and Environment

- Use `secrets: inherit` in the caller job to pass required secrets to providers.
- Your Slideflow config can continue to reference environment variables as usual.
- For Google Slides builds, ensure credentials/folder IDs used by your config are available in the caller workflow environment.
