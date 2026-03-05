# Google Sheets Modes

`workbook.tabs[].mode` controls how Slideflow writes data into each tab.

## `replace`

- Clears and rewrites the target tab from `start_cell`.
- Best default for deterministic reporting tabs.

## `append`

- Appends rows after existing tab content.
- Use when building log-like or event-like tabs.

## Recommended defaults

- Reporting tables: `replace`
- Time-series accumulation tabs: `append`

## Runtime notes

- `--threads` is bounded by tab count.
- `include_header` should be explicit per tab to avoid accidental header duplication.
- AI summaries are configured per tab under `workbook.tabs[].ai.summaries[]`.

## Validation flow

```bash
slideflow sheets doctor config.yml --strict
slideflow sheets validate config.yml
slideflow sheets build config.yml --threads 10
```
