# Citations Patterns

Use citations in Google Slides configs to retain source traceability for each run.

## Core principles

- Prefer stable model/query metadata to produce durable source links.
- Configure citations at the root `citations:` block (not slide-level fields).
- Avoid runtime-volatile values in source path metadata.

## Supported citations schema

```yaml
citations:
  enabled: true
  mode: both              # model | execution | both
  location: per_slide     # per_slide | per_section | document_end
  max_items: 25
  dedupe: true
  include_query_text: false
  repo_url_template: https://github.com/org/repo/blob/{sha}/{path}
```

## Notes on source links

- Slideflow derives citation entries from model + execution metadata.
- Use immutable commit SHAs for stable source link resolution where possible.

## Operational checks

1. Run `slideflow validate config.yml --provider-contract-check`.
2. Build one small smoke run and inspect slide notes manually.
3. Confirm citation entries are present at the configured `location`.

## Gotchas

- `mode` only accepts: `model`, `execution`, `both`.
- `location` only accepts: `per_slide`, `per_section`, `document_end`.
- If source URLs point to mutable branches, citation traceability weakens over time.
