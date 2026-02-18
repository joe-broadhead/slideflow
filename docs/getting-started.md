# Getting Started

## Prerequisites

- Python `3.12+`
- Google Cloud project with:
  - Google Slides API enabled
  - Google Drive API enabled
- A service account with access to your target template deck and Drive folders

## Install

Current stable path (until PyPI naming migration is finalized):

```bash
pip install git+https://github.com/joe-broadhead/slideflow.git
```

For editable local development:

```bash
git clone https://github.com/joe-broadhead/slideflow.git
cd slideflow
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ai,docs]"
```

## Configure Google credentials

SlideFlow accepts credentials via:

1. `provider.config.credentials` in YAML
2. `GOOGLE_SLIDEFLOW_CREDENTIALS` environment variable

`GOOGLE_SLIDEFLOW_CREDENTIALS` supports either:

- Path to service-account JSON file
- Raw JSON string content

Example:

```bash
export GOOGLE_SLIDEFLOW_CREDENTIALS=/absolute/path/service-account.json
```

## Create a template deck

Create a Google Slides template deck with placeholders and target slide layouts.
You will need:

- `template_id` (presentation ID from URL)
- slide IDs for each slide you modify

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

## Validate before build

```bash
slideflow validate config.yml
slideflow build config.yml
```

Validation should be treated as mandatory in CI and release workflows.

## Next steps

- Run the sample pipeline in [Quickstart](quickstart.md)
- Review [Configuration Reference](config-reference.md)
- Use [Cookbooks](cookbooks.md) for production patterns
