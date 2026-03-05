# Expected Command Output (Minimal Examples)

These examples are intended for authoring smoke tests. Output lines can vary by
Slideflow version; use the expected summary markers below.

## Slides example

Config: `.github/skills/slideflow-yaml-authoring/assets/examples/slides.minimal.yml`

```bash
slideflow doctor --config-file .github/skills/slideflow-yaml-authoring/assets/examples/slides.minimal.yml --strict
slideflow validate .github/skills/slideflow-yaml-authoring/assets/examples/slides.minimal.yml
slideflow build .github/skills/slideflow-yaml-authoring/assets/examples/slides.minimal.yml --dry-run
```

Expected markers:

- doctor: `Validation Complete` or provider diagnostics summary
- validate: `Validation Complete`
- build dry-run: command completes without schema/runtime config errors

## Docs example

Config: `.github/skills/slideflow-yaml-authoring/assets/examples/docs.minimal.yml`

```bash
slideflow doctor --config-file .github/skills/slideflow-yaml-authoring/assets/examples/docs.minimal.yml --strict
slideflow validate .github/skills/slideflow-yaml-authoring/assets/examples/docs.minimal.yml
slideflow build .github/skills/slideflow-yaml-authoring/assets/examples/docs.minimal.yml --dry-run
```

Expected markers:

- doctor: `Validation Complete` or provider diagnostics summary
- validate: `Validation Complete`
- build dry-run: command completes without schema/runtime config errors

## Sheets example

Config: `.github/skills/slideflow-yaml-authoring/assets/examples/sheets.minimal.yml`

```bash
slideflow sheets doctor .github/skills/slideflow-yaml-authoring/assets/examples/sheets.minimal.yml --strict
slideflow sheets validate .github/skills/slideflow-yaml-authoring/assets/examples/sheets.minimal.yml
slideflow sheets build .github/skills/slideflow-yaml-authoring/assets/examples/sheets.minimal.yml --output-json /tmp/sheets-example-result.json
```

Expected markers:

- doctor: provider diagnostics summary
- validate: `Workbook config is valid`
- build: command executes a real write path; use a disposable workbook/folder for smoke tests
