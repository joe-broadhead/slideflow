# Google Sheets Provider

The `google_sheets` provider renders workbook outputs into Google Sheets.

Unlike Slides/Docs configs (`presentation:`), Sheets builds use the `workbook:`
schema with tab-level write definitions and optional AI summary rules.

## Setup Checklist

1. Enable APIs in your Google Cloud project:
   - Google Sheets API
   - Google Drive API
2. Create a service account.
3. Share destination Drive folders (and existing target sheet, if reusing one)
   with that service account.
4. Provide credentials via:
   - `provider.config.credentials`, or
   - `GOOGLE_SHEETS_CREDENTIALS`, or
   - `GOOGLE_SLIDEFLOW_CREDENTIALS` (fallback).

## Provider Config

```yaml
provider:
  type: "google_sheets"
  config:
    credentials: "/path/to/service-account.json"
    spreadsheet_id: "<existing_sheet_id>"      # optional; reuse instead of create
    drive_folder_id: "<drive_folder_id>"       # optional; move created sheet
    share_with:
      - "team@example.com"
    share_role: "reader"                        # reader|writer|commenter
    requests_per_second: 1.0
```

Field behavior:

- `spreadsheet_id`: if set, writes into an existing spreadsheet.
- `drive_folder_id`: destination folder for newly created spreadsheets.
- `share_with` / `share_role`: optional post-build sharing.
- `requests_per_second`: Google API pacing for this build.
  - Can be overridden at runtime via `slideflow sheets build --rps ...`.

## Workbook Schema

```yaml
workbook:
  title: "Weekly KPI Snapshot"
  tabs:
    - name: "kpi_current"
      mode: "replace"
      start_cell: "A1"
      include_header: true
      data_source:
        type: "csv"
        name: "kpi_source"
        file_path: "kpi.csv"
      ai:
        summaries:
          - type: "ai_text"
            config:
              name: "kpi_narrative"             # optional; auto-generated when omitted
              provider: "openai"
              provider_args:
                model: "gpt-4o-mini"
              prompt: "Summarize weekly KPI movement in 3 bullets."
              mode: "latest"                    # latest|history
              placement:
                type: "same_sheet"              # same_sheet|summary_tab
                target_tab: "kpi_current"       # required for summary_tab; optional for same_sheet
                anchor_cell: "H2"               # required for same_sheet
                clear_range: "H2:H20"           # optional; latest mode only

    - name: "kpi_history"
      mode: "append"
      start_cell: "A1"
      include_header: false
      idempotency_key: "{week_key}"
      data_source:
        type: "csv"
        name: "kpi_history_source"
        file_path: "kpi_history.csv"
```

## Tab Write Semantics

- `mode: replace`
  - clears target tab then writes rows from `start_cell`
  - supports `include_header: true|false`
- `mode: append`
  - appends rows after existing data
  - requires `idempotency_key`
  - requires `include_header: false`
  - dedupe is tracked in reserved tab `_slideflow_meta`

Concurrency notes:

- `slideflow sheets build --threads <n>` parallelizes tab operations with a
  bounded worker pool.
- Append-mode dedupe reservation (`_slideflow_meta`) is synchronized per
  workbook to prevent duplicate run-key writes under concurrency.

## Summary Semantics

- Summaries are authored per-tab under `tabs[].ai.summaries[]`.
- Entries use a Slides/Docs-style shape: `type: ai_text` + `config`.
- `mode: latest`
  - writes fresh summary text to target cell
  - can use `clear_range` before write
- `mode: history`
  - appends a timestamped entry to existing cell text
  - `clear_range` is not allowed

Placement:

- `placement.type: summary_tab`
  - writes summary to a dedicated target tab/cell
  - requires `placement.target_tab`
  - `placement.target_tab` must be different from the source tab
- `placement.type: same_sheet`
  - writes summary into the source tab
  - `placement.target_tab` is optional; defaults to source tab
  - only supported when source tab `mode == replace`
  - runtime guard blocks writes when anchor/clear-range overlaps rendered data

### Breaking schema changes

- Removed: `workbook.summaries[]`
- Removed: `placement.tab_name`
- New location: `workbook.tabs[].ai.summaries[]`
- New key: `placement.target_tab`

Migration example:

Before:

```yaml
workbook:
  summaries:
    - name: "kpi_summary"
      source_tab: "kpi_current"
      provider: "openai"
      prompt: "Summarize"
      placement:
        type: "summary_tab"
        tab_name: "summary"
```

After:

```yaml
workbook:
  tabs:
    - name: "kpi_current"
      ai:
        summaries:
          - type: "ai_text"
            config:
              name: "kpi_summary"
              provider: "openai"
              prompt: "Summarize"
              placement:
                type: "summary_tab"
                target_tab: "summary"
```

## CLI Commands

```bash
slideflow sheets validate workbook.yml --output-json sheets-validate.json
slideflow sheets doctor workbook.yml --strict --output-json sheets-doctor.json
slideflow sheets build workbook.yml --rps 1.2 --output-json sheets-build.json
slideflow sheets build workbook.yml --threads 3 --output-json sheets-build.json
```

Build JSON includes:

- runtime controls:
  - `runtime.threads.requested`
  - `runtime.threads.applied`
  - `runtime.threads.supported_values`
  - `runtime.threads.effective_workers`
  - `runtime.threads.workload_size`
  - `runtime.requests_per_second.requested`
  - `runtime.requests_per_second.applied`
  - `runtime.requests_per_second.source`
- workbook-level counters: tabs/summaries succeeded/failed
- per-tab results (`rows_written`, `rows_skipped`, `run_key`, error)
- per-summary results (`placement_type`, `target_cell`, `chars_written`, error)

## Live Testing

```bash
export SLIDEFLOW_RUN_LIVE=1
export GOOGLE_SHEETS_CREDENTIALS=/abs/path/service-account.json
export SLIDEFLOW_LIVE_SHEETS_FOLDER_ID=<drive-folder-id>
pytest -q tests/live_tests -m live_google_sheets
```

Related references:

- [Configuration Reference](../config-reference.md)
- [CLI Reference](../cli-reference.md)
- [Automation](../automation.md)
- [Testing](../testing.md)
