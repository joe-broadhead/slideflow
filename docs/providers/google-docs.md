# Google Docs Provider

The `google_docs` provider renders SlideFlow output into Google Docs documents
using section markers (for example `{{SECTION:intro}}`) as logical anchors.

It reuses `presentation.slides[]` from the core schema:

- `slides[].id` maps to a marker id in the document template.
- replacements/charts scoped to that `slide.id` run inside the matching section.

## Setup Checklist

1. Enable APIs in your Google Cloud project:
   - Google Docs API
   - Google Drive API
2. Create a service account.
3. Share the template document (and destination Drive folders) with that service account.
4. Provide credentials via:
   - `provider.config.credentials` in YAML, or
   - `GOOGLE_DOCS_CREDENTIALS`, or
   - `GOOGLE_SLIDEFLOW_CREDENTIALS` (fallback).

## Template Design for Marker-Based Sections

Use explicit section markers in your document template:

```text
{{SECTION:intro}}
{{SECTION:regional_summary}}
{{SECTION:outlook}}
```

Rules:

- Marker ids must be unique per document.
- Marker ids should match `presentation.slides[].id` exactly.
- Markers should be plain text (do not split token text with inline objects/chips).

## Provider Config

```yaml
provider:
  type: "google_docs"
  config:
    credentials: "/path/to/service-account.json"
    template_id: "<google_docs_template_id>"
    document_folder_id: "<folder_for_output_docs>"
    drive_folder_id: "<folder_for_chart_images>"
    section_marker_prefix: "{{SECTION:"
    section_marker_suffix: "}}"
    remove_section_markers: false
    default_chart_width_pt: 300
    share_with:
      - "team@example.com"
    share_role: "reader"
    requests_per_second: 1.0
    strict_cleanup: false
```

Field behavior:

- `template_id`: if set, SlideFlow copies the document template; otherwise creates a blank doc.
- `document_folder_id`: destination folder for generated docs.
- `drive_folder_id`: destination folder for uploaded chart images.
- `section_marker_prefix` / `section_marker_suffix`: marker token format.
- `share_with` / `share_role`: post-render sharing.
- `requests_per_second`: API pacing control.
- `strict_cleanup`: fail run if chart-image cleanup fails.

Current implementation notes:

- `remove_section_markers` is currently reserved and not yet applied at render time.
- `default_chart_width_pt` is currently reserved and not yet applied at render time.

## Runtime Behavior

- Replacements are section-scoped by marker id.
- Charts are inserted inline at the matched section anchor.
- Positional chart fields (`x`, `y`, alignment) are ignored for `google_docs`.
- The build result `url` points to `https://docs.google.com/document/d/<id>`.

## Contract Validation

Use provider contract checks before build:

```bash
slideflow validate config.yml --provider-contract-check --params-path variants.csv
```

Contract checks for `google_docs` validate:

- marker presence for each configured `slide.id`
- marker uniqueness
- placeholder presence within the section body
- template fetch accessibility

Issue types:

- `template_fetch_failed`
- `missing_section_marker`
- `duplicate_section_marker`
- `missing_placeholder`

## Minimal Example

```yaml
provider:
  type: "google_docs"
  config:
    template_id: "1AbCdEf..."

presentation:
  name: "Weekly Newsletter"
  slides:
    - id: "intro"
      replacements:
        - type: "text"
          config:
            placeholder: "{{WEEK_LABEL}}"
            replacement: "Week 09"
```

## Operational Notes

- Start with conservative concurrency/rate settings and tune gradually.
- Keep markers stable after config wiring.
- Validate with `--provider-contract-check` in CI for template safety.

Related references:

- [Configuration Reference](../config-reference.md)
- [CLI Reference](../cli-reference.md)
- [Deployments](../deployments.md)
