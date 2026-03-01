# Google Slides Provider

The `google_slides` provider renders SlideFlow output into real Google Slides decks.
It can create a blank deck or copy a template, insert chart images, run text/table/AI replacements, and optionally share the final deck.

## Setup Checklist

1. Enable APIs in your Google Cloud project:
   - Google Slides API
   - Google Drive API
2. Create a service account.
3. Share the template deck (and destination Drive folder) with that service account email.
4. Supply credentials via either:
   - `provider.config.credentials` in YAML (file path or raw JSON), or
   - `GOOGLE_SLIDEFLOW_CREDENTIALS` environment variable.

## Template Design for Automation

Use a template deck that is stable and automation-friendly:

- Keep placeholder text explicit (for example `{{TITLE}}`, `{{TABLE_1,1}}`).
- Keep slide IDs stable after wiring your config.
- Reserve chart regions with enough space for your configured `x/y/width/height`.
- Avoid deleting/recreating slides after IDs are mapped in YAML.

## Getting Slide IDs

In the Google Slides editor, navigate to a target slide and inspect the URL fragment.
The slide fragment typically looks like `#slide=id.<slide_object_id>`.
Use that object ID in `presentation.slides[].id`.

## Provider Config Fields

```yaml
provider:
  type: "google_slides"
  config:
    credentials: "/path/to/service-account.json"
    template_id: "<template_presentation_id>"
    presentation_folder_id: "<folder_for_output_decks>"
    drive_folder_id: "<folder_for_chart_images>"
    new_folder_name: "Weekly Reports"
    new_folder_name_fn: "compute_subfolder_name"
    share_with:
      - "team@example.com"
    share_role: "reader"
    transfer_ownership_to: "owner@example.com"
    transfer_ownership_strict: false
    requests_per_second: 1.0
    strict_cleanup: false
```

If you use `GOOGLE_SLIDEFLOW_CREDENTIALS`, you can omit `config.credentials`.

Field behavior:

- `template_id`: if set, SlideFlow copies the template instead of creating a blank deck.
- `presentation_folder_id`: destination folder for generated decks.
- `drive_folder_id`: destination folder for uploaded chart images.
  - If omitted, SlideFlow falls back to the presentation destination folder logic.
- `new_folder_name` + `new_folder_name_fn`: optional dynamic subfolder under `presentation_folder_id`.
- `share_with` + `share_role`: shares the rendered deck after generation.
- `transfer_ownership_to`: optional ownership handoff target after successful render/share.
- `transfer_ownership_strict`: if `true`, ownership handoff failure fails the run.
- `requests_per_second`: throttles API calls.
- `strict_cleanup`: if `true`, cleanup failures (chart image trash) fail the render.

## Sharing and Permissions

Sharing is performed by the service account, not your personal user.

- Ensure the service account has permission to share files in the target drive/folder.
- `share_role` supports `reader`, `writer`, and `commenter`.
- Google may send notification emails when sharing is executed.
- Ownership transfer is explicit opt-in and only works for files in **My Drive** (not Shared Drives).
- Transfer uses Google Drive ownership APIs and may notify the target owner.

## Cleanup Semantics

Chart images are uploaded to Drive so Slides can reference them.
After render, SlideFlow attempts to trash those images.

- Default behavior: cleanup issues are logged but do not fail the run.
- With `strict_cleanup: true`: cleanup failure raises an error and fails the run.

## Performance and Quotas

For bulk generation, tune both concurrency and API pacing:

- CLI concurrency: `slideflow build ... --threads <n>`
- API rate limit: `slideflow build ... --rps <float>` or `provider.config.requests_per_second`

Start conservative (for example `--threads 2`, `--rps 0.8`) and increase gradually.

## Common Failures

- `404`/`403` on template copy: service account cannot access template deck.
- `403` on folder writes: service account lacks folder-level permissions.
- Replacement count is zero: placeholder text in template does not exactly match YAML placeholder.
- Deck created but no charts: chart generation failed before insertion (check chart logs and data source validity).
