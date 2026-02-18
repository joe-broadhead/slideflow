# CLI Reference

## Command overview

```bash
slideflow [GLOBAL_OPTIONS] COMMAND [ARGS] [OPTIONS]
```

Commands:

- `build`: validate + generate one or many presentations
- `validate`: validate configuration and registries without rendering

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

Registry resolution order:

1. CLI `--registry` paths (if provided)
2. `registry:` in config YAML (if provided)
3. local `./registry.py` (if present)

Examples:

```bash
slideflow validate config.yml
slideflow validate config.yml --registry registry.py
slideflow validate config.yml -r base_registry.py -r team_registry.py
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

Registry resolution order:

1. CLI `--registry` paths (if provided)
2. `registry:` in config YAML (if provided)
3. local `./registry.py` (if present)

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
```

## Exit behavior

- Returns non-zero exit status on validation/build failures
- CI should treat any non-zero status as a failed job
