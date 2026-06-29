# Google Slides Provider

The `google_slides` provider renders SlideFlow output into real Google Slides decks.
It can create a blank deck or copy a template, insert chart images, run text/table/AI replacements, and optionally share the final deck.

## Setup Checklist

1. Enable APIs in your Google Cloud project:
   - Google Slides API
   - Google Drive API
2. Create or select the Google identity SlideFlow will run as. This can be a
   service account key, Workload Identity Federation, or runtime ADC identity.
3. Share the template deck (and destination Drive folder) with that identity.
4. Supply credentials via either:
   - `provider.config.credentials` in YAML as service-account JSON or a path to an untracked service-account file, or
   - `GOOGLE_SLIDEFLOW_CREDENTIALS` environment variable, or
   - `GOOGLE_APPLICATION_CREDENTIALS`, or
   - runtime Application Default Credentials.

`GOOGLE_SLIDEFLOW_CREDENTIALS` accepts service-account JSON or external-account
/ Workload Identity Federation JSON as a file path or raw JSON payload. Use
that environment source, `GOOGLE_APPLICATION_CREDENTIALS`, or runtime ADC for
WIF. Do not commit raw credential JSON or `.env` files.

For production Shared Drive setup and command-by-command service-account
bootstrap, see [Google Service Accounts & Shared Drives](../google-service-accounts-shared-drives.md).

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
    credentials: null # set GOOGLE_SLIDEFLOW_CREDENTIALS or use an untracked path
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
    chart_image_sharing_mode: "restricted" # restricted | public
    strict_restricted_chart_cleanup: true
    requests_per_second: 1.0
    strict_cleanup: false
    allow_partial_render: false
```

If you use `GOOGLE_SLIDEFLOW_CREDENTIALS`, `GOOGLE_APPLICATION_CREDENTIALS`, or
runtime ADC, you can omit `config.credentials`.

Field behavior:

- `template_id`: if set, SlideFlow copies the template instead of creating a blank deck.
- `presentation_folder_id`: destination folder for generated decks.
- `drive_folder_id`: destination folder for uploaded chart images.
  - If omitted, SlideFlow falls back to the presentation destination folder logic.
- `new_folder_name` + `new_folder_name_fn`: optional dynamic subfolder under `presentation_folder_id`.
- `share_with` + `share_role`: shares the rendered deck after generation; `share_role` defaults to `reader`.
- `transfer_ownership_to`: optional ownership handoff target after successful render/share.
- `transfer_ownership_strict`: if `true`, ownership handoff failure fails the run.
- `chart_image_sharing_mode`: uploaded chart-image ACL mode:
  - `restricted` (default): keeps uploaded Drive files private at rest, grants temporary non-discoverable access for chart insertion, then revokes it.
  - `public`: keeps `anyone:reader` access after insertion and logs a warning because generated chart images may contain sensitive data.
- `strict_restricted_chart_cleanup`: with restricted chart images, fail the run
  by default if temporary public access cannot be revoked or uploaded chart
  images cannot be cleaned up. Set `false` only for explicitly reviewed
  best-effort cleanup behavior.
- `requests_per_second`: throttles API calls.
- `strict_cleanup`: if `true`, cleanup failures (chart image trash) fail the render.
- `allow_partial_render`: defaults to `false`; chart/replacement failures fail
  the render instead of silently producing incomplete decks. Set `true` to
  continue and inspect `content_errors` in the build result.

## Sharing and Permissions

Sharing is performed by the service account, not your personal user.

- Ensure the service account has permission to share files in the target drive/folder.
- `share_role` supports `reader`, `writer`, and `commenter`; omit it for least-privilege reader access and set `writer` only when recipients must edit.
- Google may send notification emails when sharing is executed.
- Ownership transfer is explicit opt-in and only works for files in **My Drive** (not Shared Drives).
- Transfer uses Google Drive ownership APIs and may notify the target owner.

For Shared Drive-first permission patterns and ownership-transfer constraints,
see [Google Service Accounts & Shared Drives](../google-service-accounts-shared-drives.md).

## Contract Validation

Use provider contract checks before build:

```bash
slideflow validate config.yml --provider-contract-check --params-path variants.csv
```

Contract checks use read-only Google Slides auth scopes by default. If read-only
auth initialization fails, validation fails closed unless you explicitly pass
`--provider-contract-full-auth-fallback`.

## Cleanup Semantics

Chart images are uploaded to Drive so Slides can reference them.
After render, SlideFlow attempts to trash those images.

- Default restricted-mode behavior: temporary-access revoke or cleanup failure
  raises an error and fails the run.
- With `chart_image_sharing_mode: public`, cleanup issues are logged unless
  `strict_cleanup: true` is set.
- Cleanup emits a summary log and build-result fields with deleted/failed counts and failed file IDs when applicable.

## Citation Rendering

When `citations.enabled: true`, SlideFlow renders a `Sources` block into
speaker notes.

- `citations.location: per_slide`:
  - each slide receives its own notes-level citation block.
- `citations.location: document_end`:
  - citations are deduplicated and written to the first slide notes.

For Google Slides, `per_section` behaves the same as `per_slide`.

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
