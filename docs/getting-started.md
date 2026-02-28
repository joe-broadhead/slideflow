# Getting Started

## Prerequisites

- Python `3.12+`
- Google Cloud project with:
  - Google Slides API enabled
  - Google Docs API enabled (if using `google_docs` provider)
  - Google Drive API enabled
- A service account with access to your target template deck/document and Drive folders

## Install

Install from PyPI:

```bash
pip install slideflow-presentations
```

For editable local development:

```bash
git clone https://github.com/joe-broadhead/slideflow.git
cd slideflow
uv sync --extra dev --extra ai --extra docs --locked
source .venv/bin/activate
```

## Configure Google credentials

SlideFlow accepts credentials via:

1. `provider.config.credentials` in YAML
2. `GOOGLE_DOCS_CREDENTIALS` environment variable (for `google_docs`)
3. `GOOGLE_SLIDEFLOW_CREDENTIALS` environment variable

Environment credential values support either:

- Path to service-account JSON file
- Raw JSON string content

Example:

```bash
export GOOGLE_SLIDEFLOW_CREDENTIALS=/absolute/path/service-account.json
export GOOGLE_DOCS_CREDENTIALS=/absolute/path/service-account.json
```

## Create a template deck

Create a template and decide provider mode:

- `google_slides`: Google Slides template deck with placeholder text and target slide IDs.
- `google_docs`: Google Docs template with explicit section markers (for example `{{SECTION:intro}}`).

You will need:

- `template_id` (presentation/document ID from URL)
- `google_slides`: slide IDs for each slide you modify
- `google_docs`: marker ids that match `presentation.slides[].id`

## Minimal config

```yaml
provider:
  type: "google_slides"
  config:
    credentials: "/path/to/credentials.json"
    template_id: "your_template_presentation_id"

presentation:
  name: "My First SlideFlow Deck"
  slides:
    - id: "your_slide_id"
      replacements:
        - type: "text"
          config:
            placeholder: "{{TITLE}}"
            replacement: "Hello SlideFlow"
```

Google Docs variant:

```yaml
provider:
  type: "google_docs"
  config:
    template_id: "your_google_docs_template_id"

presentation:
  name: "My First SlideFlow Doc"
  slides:
    - id: "intro"
      replacements:
        - type: "text"
          config:
            placeholder: "{{TITLE}}"
            replacement: "Hello SlideFlow"
```

## Validate before build

```bash
slideflow validate config.yml
slideflow build config.yml
```

Validation should be treated as mandatory in CI and release workflows.

For provider contract checks (recommended in CI):

```bash
slideflow validate config.yml --provider-contract-check
```

To discover built-in chart templates:

```bash
slideflow templates list --details
slideflow templates info bars/bar_basic
```

## Quick smoke check (recommended after install)

Run the checked-in smoke sample with no external credentials:

```bash
cd docs/quickstart/smoke
slideflow validate config.yml
slideflow build config.yml --params-path params.csv --dry-run
```

## Next steps

- Run the sample pipeline in [Quickstart](quickstart.md)
- Configure real template/folder/sharing behavior in [Google Slides Provider](providers/google-slides.md)
- Configure marker-based doc behavior in [Google Docs Provider](providers/google-docs.md)
- Choose and harden source systems in [Data Connectors](data-connectors.md)
- Add reusable preprocessing in [Data Transforms](data-transforms.md)
- Configure LLM output in [AI Providers](ai-providers.md)
- Plan production scheduling in [Deployments](deployments.md)
- Review [Configuration Reference](config-reference.md)
- Use [Cookbooks](cookbooks.md) for production patterns
