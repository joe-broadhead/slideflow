# PowerPoint Provider

The `powerpoint` provider renders SlideFlow output into native local `.pptx`
files. It uses an existing PowerPoint template, applies replacements and chart
insertions, and saves the generated deck to `output_dir`.

## Install

PowerPoint support is optional:

```bash
pip install "slideflow-presentations[powerpoint]"
```

For local development:

```bash
uv sync --extra dev --extra ai --extra powerpoint --locked
```

## Template Design

Use a stable `.pptx` template:

- Put placeholders directly in text boxes or table cells, for example `{{TITLE}}`.
- Use one-based slide indexes (`"1"`, `"2"`) for simple configs, or native
  PowerPoint `slide_id` values when you need IDs that survive slide reordering.
- Reserve chart regions with enough room for your configured `x`, `y`, `width`,
  and `height` values. Positioning values are interpreted as points.

## Provider Config

```yaml
provider:
  type: "powerpoint"
  config:
    template_path: "./templates/report.pptx"
    output_dir: "./dist"
    slide_id_mode: "auto" # auto | index | native
    read_only_template: true
    file_collision_strategy: "fail" # fail | overwrite | suffix
    strict_cleanup: false
    allow_partial_render: false
```

Field behavior:

- `template_path`: required path to the source `.pptx` file.
- `output_dir`: destination directory for generated `.pptx` files.
- `slide_id_mode`:
  - `auto` (default): numeric slide IDs resolve as one-based indexes first,
    then native PowerPoint `slide_id` values.
  - `index`: only one-based slide indexes are accepted.
  - `native`: only native PowerPoint slide IDs are accepted.
- `read_only_template`: prevents writes to `template_path`; keep this `true`
  for production runs.
- `file_collision_strategy`:
  - `fail` (default): fail if the output path already exists.
  - `overwrite`: replace an existing output file.
  - `suffix`: write `Deck-1.pptx`, `Deck-2.pptx`, etc. when needed.
- `strict_cleanup`: applies to temporary in-memory chart image cleanup.
- `allow_partial_render`: defaults to `false`; chart/replacement failures fail
  the render instead of silently producing incomplete `.pptx` files. Set
  `true` only for best-effort output and inspect `content_errors`.

## Example

```yaml
provider:
  type: "powerpoint"
  config:
    template_path: "./templates/monthly-report.pptx"
    output_dir: "./build"
    file_collision_strategy: "suffix"

presentation:
  name: "Monthly Report"
  slides:
    - id: "1"
      replacements:
        - type: "text"
          config:
            placeholder: "{{TITLE}}"
            replacement: "June Revenue"
      charts:
        - type: "plotly_go"
          config:
            title: "Revenue"
            x: 72
            y: 144
            width: 432
            height: 252
            traces:
              - type: "bar"
                x: ["North", "South"]
                y: [120, 98]
```

## Contract Validation

Use provider contract checks before build:

```bash
slideflow validate config.yml --provider-contract-check
```

Contract checks open the local `.pptx` template and validate:

- configured slide IDs against `slide_id_mode`
- configured replacement placeholders in slide text boxes
- configured replacement placeholders in table cells

For variant builds, pass a params CSV column that renders
`provider.config.template_path` (for example a `{template_path}` token):

```bash
slideflow validate config.yml --provider-contract-check --params-path variants.csv
```

## Current Scope

- Native `.pptx` output is supported.
- Sharing is a no-op because artifacts are local files.
- Citations are not rendered into speaker notes in V1 because `python-pptx`
  does not expose a stable public speaker-notes API.
- LibreOffice/PDF conversion is intentionally out of scope for this provider.
