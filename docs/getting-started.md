# Getting Started

## 1. Install SlideFlow

Install from PyPI:

```bash
pip install slideflow
```

If you need the latest unreleased version:

```bash
pip install git+https://github.com/joe-broadhead/slideflow.git
```

## 2. Prepare Google credentials

SlideFlow requires a Google service account with access to:

- Google Slides API
- Google Drive API

You can provide credentials either:

- In provider config: `provider.config.credentials`
- Via environment variable: `GOOGLE_SLIDEFLOW_CREDENTIALS`

`GOOGLE_SLIDEFLOW_CREDENTIALS` may be either:

- Path to credentials JSON file
- Raw JSON credentials string

## 3. Create a template slide deck

Create a Google Slides deck that contains your layout/placeholders.
You will need:

- Template presentation ID
- Slide IDs for each slide you plan to update

## 4. Create a config file

Minimal example:

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

## 5. Validate then build

```bash
slideflow validate config.yml
slideflow build config.yml
```

Validation should be part of your normal workflow before `build`, especially for batch runs.
