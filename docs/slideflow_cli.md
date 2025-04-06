# Slideflow CLI Commands

This document outlines all the commands available in the `slideflow` CLI and how to use them.

---

## 🧱 `build`

**Builds a single presentation based on a YAML config.**

```bash
slideflow build config.yml --registry myproject.registry
```

### Options:
- `config.yml`: Path to the config file defining the presentation.
- `--registry`: (Optional) Python path to a function registry.

---

## 🧱 `build-bulk`

**Builds multiple presentations using a parameter file and shared data manager.**

```bash
slideflow build-bulk run config.yml --param-file params.csv --max-workers 4 --registry myproject.registry
```

### Options:
- `config.yml`: Base config file (used as a template).
- `--param-file`: CSV file with one row per presentation (e.g., different stores, categories etc).
- `--max-workers`: (Optional) Number of parallel threads.
- `--registry`: (Optional) Python path to a function registry.

---

## 👀 `preview`

**Previews the structure of a single or bulk presentation config.**

```bash
slideflow preview-bulk config.yml --param-file params.csv --registry myproject.registry
```

---

## ✅ `validate`

**Validates the structure and schema of your config file.**

```bash
slideflow validate config.yml --registry myproject.registry
```

---

## 💾 `extract-sources`

**Extracts and saves datasets from the config’s data sources.**

```bash
slideflow extract-sources run config.yml --format csv --output-dir ./outputs
```

### Options:
- `--source`: (Optional) Only extract one source by name.
- `--format`: csv, json, or parquet.
- `--output-dir`: Directory to save outputs.

---

## ℹ️ Notes

- Function registries can be loaded from:
  - `--registry` CLI flag
  - Or from the `pyproject.toml` using an entry point like:

```toml
[project.entry-points.slideflow_registry]
default = "myproject.registry:function_registry"
```

- All configs use Pydantic for validation and support rich customization with preprocessing and value functions.
