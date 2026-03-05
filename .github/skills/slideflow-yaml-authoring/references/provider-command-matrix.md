# Provider Command Matrix

## Google Slides

```bash
slideflow doctor --config-file config.yml --strict
slideflow validate config.yml --provider-contract-check
slideflow build config.yml --threads 10
```

## Google Docs

```bash
slideflow doctor --config-file config.yml --strict
slideflow validate config.yml --provider-contract-check
slideflow build config.yml --threads 10
```

## Google Sheets

```bash
slideflow sheets doctor config.yml --strict
slideflow sheets validate config.yml
slideflow sheets build config.yml --threads 10
```

## Batch params smoke-test pattern

1. Build a single-row params CSV for one region/entity first.
2. Run `doctor` + `validate` on the real config.
3. Run one small `build` before full-params execution.

## Runnable minimal examples

- `.github/skills/slideflow-yaml-authoring/assets/examples/slides.minimal.yml`
- `.github/skills/slideflow-yaml-authoring/assets/examples/docs.minimal.yml`
- `.github/skills/slideflow-yaml-authoring/assets/examples/sheets.minimal.yml`
- `.github/skills/slideflow-yaml-authoring/assets/examples/expected-command-output.md`
