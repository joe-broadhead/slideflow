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
2. Create or select the Google identity SlideFlow will run as. This can be a
   service account key, Workload Identity Federation, or runtime ADC identity.
3. Share the template document (and destination Drive folders) with that identity.
4. Provide credentials via:
   - `provider.config.credentials` in YAML as service-account JSON or a path to an untracked service-account file, or
   - `GOOGLE_DOCS_CREDENTIALS`, or
   - `GOOGLE_SLIDEFLOW_CREDENTIALS` (fallback), or
   - `GOOGLE_APPLICATION_CREDENTIALS`, or
   - runtime Application Default Credentials.

`GOOGLE_DOCS_CREDENTIALS` and `GOOGLE_SLIDEFLOW_CREDENTIALS` accept
service-account JSON or external-account / Workload Identity Federation JSON as
a file path or raw JSON payload. Use those environment sources,
`GOOGLE_APPLICATION_CREDENTIALS`, or runtime ADC for WIF. Do not commit raw
credential JSON or `.env` files.

For production Shared Drive setup and service-account bootstrap commands, see
[Google Service Accounts & Shared Drives](../google-service-accounts-shared-drives.md).

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
    credentials: null # set GOOGLE_DOCS_CREDENTIALS or use an untracked path
    template_id: "<google_docs_template_id>"
    document_folder_id: "<folder_for_output_docs>"
    drive_folder_id: "<folder_for_chart_images>"
    section_marker_prefix: "{{SECTION:"
    section_marker_suffix: "}}"
    remove_section_markers: false
    default_chart_width_pt: 480
    share_with:
      - "team@example.com"
    share_role: "reader"
    transfer_ownership_to: "owner@example.com"
    transfer_ownership_strict: false
    chart_image_sharing_mode: "restricted" # restricted | public
    strict_restricted_chart_cleanup: true
    requests_per_second: 1.0
    strict_cleanup: false
    allow_partial_render: false
```

Field behavior:

- `template_id`: if set, SlideFlow copies the document template; otherwise creates a blank doc.
- `document_folder_id`: destination folder for generated docs.
- `drive_folder_id`: destination folder for uploaded chart images.
- `section_marker_prefix` / `section_marker_suffix`: marker token format.
- `share_with` / `share_role`: post-render sharing; `share_role` defaults to `reader`.
- `transfer_ownership_to`: optional ownership handoff target after successful render/share.
- `transfer_ownership_strict`: if `true`, ownership handoff failure fails the run.
- `chart_image_sharing_mode`: uploaded chart-image ACL mode:
  - `restricted` (default): keeps uploaded Drive files private at rest, grants temporary non-discoverable access for chart insertion, then revokes it.
  - `public`: keeps `anyone:reader` access after insertion and logs a warning because generated chart images may contain sensitive data.
- `strict_restricted_chart_cleanup`: with restricted chart images, fail the run
  by default if temporary public access cannot be revoked or uploaded chart
  images cannot be cleaned up. Set `false` only for explicitly reviewed
  best-effort cleanup behavior.
- `requests_per_second`: API pacing control.
- `strict_cleanup`: fail run if chart-image cleanup fails.
- `allow_partial_render`: defaults to `false`; chart/replacement failures fail
  the render instead of silently producing incomplete docs. Set `true` to
  continue and inspect `content_errors` in the build result.

Current implementation notes:

- `remove_section_markers` runs after render finalization and deletes section-marker tokens.
- `default_chart_width_pt` defaults to `480`; it is reserved for future inline
  chart sizing behavior and is not currently applied at render time.

## Runtime Behavior

- Replacements are section-scoped by marker id.
- Charts are inserted inline at the matched section anchor.
- Positional chart fields (`x`, `y`, alignment) are ignored for `google_docs` and log a warning when non-zero positional values are provided.
- The build result `url` points to `https://docs.google.com/document/d/<id>`.
- Ownership transfer is explicit opt-in and only supported for files in **My Drive** (not Shared Drives).

For Shared Drive-first patterns and ownership-transfer constraints, see
[Google Service Accounts & Shared Drives](../google-service-accounts-shared-drives.md).

## Citation Rendering

When `citations.enabled: true`, Google Docs rendering supports two modes:

- `citations.location: per_section` (or `per_slide`):
  - creates section-scoped footnotes with a `Sources` block.
- `citations.location: document_end`:
  - appends a deduplicated `Sources` section to the document end.

Citation payloads are also included in build JSON output for downstream audit
or notification workflows.

## Contract Validation

Use provider contract checks before build:

```bash
slideflow validate config.yml --provider-contract-check --params-path variants.csv
```

Contract checks use read-only Google Docs auth scopes by default. If read-only
auth initialization fails, validation fails closed unless you explicitly pass
`--provider-contract-full-auth-fallback`.

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
- Cleanup logs and build-result fields include deleted/failed chart-image totals and failed file IDs when applicable.

Related references:

- [Configuration Reference](../config-reference.md)
- [CLI Reference](../cli-reference.md)
- [Deployments](../deployments.md)
