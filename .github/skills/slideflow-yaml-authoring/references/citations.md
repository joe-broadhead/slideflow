# Citations Patterns

Use citations in Google Slides configs to retain source traceability for each run.

## Core principles

- Prefer stable source identifiers (model alias, file path, or table name).
- Keep citation scope explicit: deck-level or per-slide.
- Avoid runtime-volatile values in source labels.

## Deck-level citations (single source block for all slides)

```yaml
citations:
  mode: deck
  sources:
    - label: channel_performance (dbt model)
      url: https://github.com/org/repo/blob/<sha>/analyses/slide__channel_performance.sql
```

## Per-slide citations

```yaml
presentation:
  slides:
    - id: g123abc_0_0
      citations:
        mode: per_slide
        sources:
          - label: country_gmv_growth_share (dbt model)
            url: https://github.com/org/repo/blob/<sha>/analyses/slide__country_gmv_growth_share.sql
```

## Operational checks

1. Run `slideflow validate config.yml --provider-contract-check`.
2. Build one small smoke run and inspect slide notes manually.
3. Confirm all expected source labels are present and correctly mapped.

## Gotchas

- If source URLs point to mutable branches, citation traceability weakens over time.
- Missing slide-level citation blocks can produce uneven source attribution across the deck.

