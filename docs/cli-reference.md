# CLI Reference

## Command overview

```bash
slideflow [GLOBAL_OPTIONS] COMMAND [ARGS] [OPTIONS]
```

Commands:

- `build`: validate + generate one or many presentations
- `validate`: validate configuration and registries without rendering
- `doctor`: run preflight diagnostics for runtime dependencies
- `templates`: inspect available chart templates and contracts

## Global options

| Option | Description |
| --- | --- |
| `-v`, `--verbose` | INFO-level logging |
| `--debug` | DEBUG-level logging |
| `-q`, `--quiet` | ERROR-only logging |

## `slideflow validate`

```bash
slideflow validate CONFIG_FILE [OPTIONS]
```

Options:

| Option | Description |
| --- | --- |
| `-r`, `--registry` | One or more Python registry files |
| `-f`, `--params-path` | Optional CSV used for provider contract checks (`template_id` column) |
| `--provider-contract-check` | Validate provider template contracts (`google_slides`: slide IDs/placeholders, `google_docs`: section markers/placeholders) |
| `--output-json` | Write machine-readable validation summary JSON |

Registry resolution order:

1. CLI `--registry` paths (if provided)
2. `registry:` in config YAML (if provided)
3. `<config_dir>/registry.py` (if present)
4. local `./registry.py` only when config-dir default is missing

Examples:

```bash
slideflow validate config.yml
slideflow validate config.yml --registry registry.py
slideflow validate config.yml -r base_registry.py -r team_registry.py
slideflow validate config.yml --output-json validate-result.json
slideflow validate config.yml --provider-contract-check --params-path variants.csv
```

## `slideflow build`

```bash
slideflow build CONFIG_FILE [OPTIONS]
```

Options:

| Option | Description |
| --- | --- |
| `-r`, `--registry` | One or more Python registry files |
| `-f`, `--params-path` | CSV file for batch generation |
| `--dry-run` | Validate all variants without rendering |
| `-t`, `--threads` | Number of concurrent presentation workers |
| `--rps` | Override provider requests/second |
| `--output-json` | Write machine-readable build summary JSON |

Registry resolution order:

1. CLI `--registry` paths (if provided)
2. `registry:` in config YAML (if provided)
3. `<config_dir>/registry.py` (if present)
4. local `./registry.py` only when config-dir default is missing

Batch parameters:

- CSV headers map to `{param}` in YAML
- Empty parameter CSVs are rejected
- Use `--dry-run` to validate all rows before expensive API calls

Examples:

```bash
slideflow build config.yml

slideflow build config.yml --dry-run

slideflow build config.yml \
  --registry registry.py \
  --params-path variants.csv

slideflow build config.yml \
  --threads 3 \
  --rps 0.8

slideflow build config.yml \
  --params-path variants.csv \
  --output-json build-result.json
```

## `slideflow doctor`

```bash
slideflow doctor [OPTIONS]
```

Options:

| Option | Description |
| --- | --- |
| `-c`, `--config-file` | Optional config file for provider-level checks |
| `-r`, `--registry` | Optional registry paths used with `--config-file` |
| `--strict` | Exit non-zero when error-severity checks fail |
| `--output-json` | Write machine-readable doctor summary JSON |

Examples:

```bash
slideflow doctor
slideflow doctor --config-file config.yml --registry registry.py
slideflow doctor --config-file config.yml --strict --output-json doctor-result.json
```

## `slideflow templates list`

```bash
slideflow templates list [OPTIONS]
```

Options:

| Option | Description |
| --- | --- |
| `-d`, `--details` | Include template descriptions |

Examples:

```bash
slideflow templates list
slideflow templates list --details
```

## `slideflow templates info`

```bash
slideflow templates info TEMPLATE_NAME
```

Examples:

```bash
slideflow templates info bars/bar_basic
slideflow templates info bar_basic
```

## Exit behavior

- Returns non-zero exit status on validation/build failures
- `doctor --strict` returns non-zero when error checks fail
- CLI failures include stable error codes in stderr output for automation parsing
- CI should treat any non-zero status as a failed job
