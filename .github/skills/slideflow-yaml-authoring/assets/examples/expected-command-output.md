# Expected Command Output (Minimal Examples)

These examples are intended for authoring smoke tests. Output lines can vary by
Slideflow version; use the expected summary markers below.

## Slides example

Config: `assets/examples/slides.minimal.yml`

```bash
slideflow doctor --config-file assets/examples/slides.minimal.yml --strict
slideflow validate assets/examples/slides.minimal.yml
slideflow build assets/examples/slides.minimal.yml --dry-run
```

Expected markers:

- doctor: `Validation Complete` or provider diagnostics summary
- validate: `Validation Complete`
- build dry-run: command completes without schema/runtime config errors

## Docs example

Config: `assets/examples/docs.minimal.yml`

```bash
slideflow doctor --config-file assets/examples/docs.minimal.yml --strict
slideflow validate assets/examples/docs.minimal.yml
slideflow build assets/examples/docs.minimal.yml --dry-run
```

Expected markers:

- doctor: `Validation Complete` or provider diagnostics summary
- validate: `Validation Complete`
- build dry-run: command completes without schema/runtime config errors

## Sheets example

Config: `assets/examples/sheets.minimal.yml`

```bash
slideflow sheets doctor assets/examples/sheets.minimal.yml --strict
slideflow sheets validate assets/examples/sheets.minimal.yml
slideflow sheets build assets/examples/sheets.minimal.yml --output-json /tmp/sheets-example-result.json
```

Expected markers:

- doctor: provider diagnostics summary
- validate: `Workbook config is valid`
- build dry-run: command completes without schema/runtime config errors
