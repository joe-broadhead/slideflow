# 🚀 SlideFlow

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Docs](https://img.shields.io/badge/docs-mkdocs%20material-blue.svg?logo=materialformkdocs&logoColor=white)](https://joe-broadhead.github.io/slideflow/)
[![Release](https://img.shields.io/github/v/release/joe-broadhead/slideflow?label=release&logo=github)](https://github.com/joe-broadhead/slideflow/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/joe-broadhead/slideflow/ci.yml?branch=master&label=CI)](https://github.com/joe-broadhead/slideflow/actions/workflows/ci.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

```
  ____  _ _     _       __ _                
 / ___|| (_) __| | ___ / _| | _____      __ 
 \___ \| | |/ _` |/ _ \ |_| |/ _ \ \ /\ / / 
  ___) | | | (_| |  __/  _| | (_) \ V  V /  
 |____/|_|_|\__,_|\___|_| |_|\___/ \_/\_/   

         Generate
     Beautiful slides.
       Direct from your data.
```

**SlideFlow is a Python-based tool for generating beautiful, data-driven decks, docs, and sheets directly from your data sources.**

[Key Features](#-key-features) • [How It Works](#-how-it-works) • [Installation](#-installation) • [Getting Started](#-getting-started) • [CLI Usage](#-cli-usage) • [Configuration](#-configuration) • [Customization](#-customization) • [Contributing](CONTRIBUTING.md)

</div>

---

## ✨ Why SlideFlow?

SlideFlow was built to solve a simple problem: automating the tedious process of creating data-heavy presentations. If you find yourself repeatedly copying and pasting charts and metrics into slide decks, SlideFlow is for you.

-   🎨 **Beautiful, Consistent Visuals:** Leverage the power of Plotly for stunning, replicable charts. Use YAML templates to create a library of reusable chart designs.
-   📊 **Connect Directly to Your Data:** Pull data from CSV files, JSON, Databricks, DuckDB, or your dbt models. No more manual data exports.
-   ⚡ **Automate Your Reporting:** Stop the manual work. Reduce errors and save time. Your decks/docs/sheets are always up-to-date with your latest data.
-   🚀 **Scale Instantly:** Need to create a presentation for every customer, region, or product? Generate hundreds of personalized presentations at once from a single template.
-   🤖 **Production Automation Ready:** Run scheduled builds in GitHub Actions with the reusable SlideFlow workflow and machine-readable JSON outputs.

---

## 🔑 Key Features

-   **Declarative YAML Configuration:** Define your entire presentation in a simple, human/agent readable YAML file.
-   **Multiple Data Source Connectors:**
    -   `csv`: For local CSV files.
    -   `json`: For local JSON files.
    -   `databricks`: For running SQL queries directly against Databricks.
    -   `dbt`: Composable dbt source config with explicit `dbt` + `warehouse` blocks.
    -   `databricks_dbt`: Legacy dbt connector format (still supported for compatibility).
-   **Dynamic Content Replacements:**
    -   **Text:** Replace simple placeholders like `{{TOTAL_REVENUE}}` with dynamic values.
    -   **Tables:** Populate entire tables in your slides from a DataFrame.
    -   **AI-Generated Text:** Use OpenAI or Gemini to generate summaries, insights, or any other text, right from your data.
-   **Powerful Charting Engine:**
    -   **Plotly Graph Objects:** Create any chart you can imagine with the full power of Plotly.
    -   **YAML Chart Templates:** Use packaged built-ins or define reusable local templates.
    -   **Custom Python Functions:** For when you need complete control over your chart generation logic.
-   **Extensible and Customizable:**
    -   Use **Function Registries** to extend SlideFlow with your own Python functions for data transformations, formatting, and more.
-   **Powerful CLI:**
    -   `slideflow build`: Generate one or many presentations.
    -   `slideflow validate`: Validate your configuration before you build.
    -   `slideflow doctor`: Run preflight diagnostics before validate/build.
    -   `slideflow sheets validate|build|doctor`: Validate/build/diagnose workbook pipelines.
    -   `slideflow templates`: Inspect available template names and parameter contracts.
    -   Generate multiple presentations from a single template using a CSV parameter file.
-   **Multiple Output Providers:**
    -   `google_slides`: Build slide decks from template slides.
    -   `google_docs`: Build marker-anchored documents for newsletter/report workflows.
    -   `google_sheets`: Build workbook outputs with tab-level replace/append semantics.
-   **Optional Source Citations:**
    -   Emit deterministic source provenance (`model` and/or `execution`) into output artifacts.
    -   Render `Sources` blocks in Slides speaker notes or Docs footnotes/document end.
    -   Capture citation payloads in `slideflow build --output-json` for downstream audit workflows.

---

## 🔧 How It Works

SlideFlow works in three simple steps:

1.  **Define:** You create a YAML file that defines your build target. This includes a Google Slides template, Google Docs template, or Google Sheets workbook schema, plus data sources and per-section/tab content.
2.  **Connect & Transform:** SlideFlow connects to your specified data sources, fetches the data, and applies any transformations you\'ve defined.
3.  **Build:** SlideFlow creates a new deck/document/workbook, populates it with your data and charts, and saves it to Google Drive.

---

## 🛠 Installation

```bash
pip install slideflow-presentations
```

Connector extras (install only what you need):

```bash
# Databricks SQL sources
pip install "slideflow-presentations[databricks]"

# dbt sources (includes dbt-core adapter stack + Git clone support)
pip install "slideflow-presentations[dbt]"

# Optional warehouse extras for dbt warehouse.type variants
pip install "slideflow-presentations[bigquery]"
pip install "slideflow-presentations[duckdb]"
```

---

## 🧑‍💻 Getting Started

To create your first output, you\'ll need:

1.  **A Template/Target:** Use either:
    - Google Slides template with slide IDs for target slides, or
    - Google Docs template with section markers like `{{SECTION:intro}}`, or
    - Google Sheets target (`spreadsheet_id`) or destination folder for workbook creation.
2.  **Your Data:** Have your data ready in a CSV file, or have your Databricks credentials configured.
3.  **A YAML Configuration File:** This is where you\'ll define your presentation. See the [Configuration](#-configuration) section for more details.
4.  **Google Cloud Credentials:** You'll need a Google Cloud service account with access to the required Google APIs (Slides/Docs/Sheets + Drive as needed). Provide credentials with one of:

    -   Set the `credentials` field in your `config.yml` to the path of your JSON credentials file.
    -   Set the `credentials` field in your `config.yml` to the JSON content of your credentials file as a string.
    -   Set `GOOGLE_DOCS_CREDENTIALS` (for `google_docs`), `GOOGLE_SHEETS_CREDENTIALS` (for `google_sheets`), or `GOOGLE_SLIDEFLOW_CREDENTIALS` (shared fallback) to a path/raw JSON.

Once you have these, you can run the `build` command:

```bash
slideflow build your_config.yml
```

---

## ⚙️ CLI Usage

SlideFlow comes with a simple CLI.

### Commands

-   `slideflow validate CONFIG_FILE [OPTIONS]`
    -   validate config/registry resolution
    -   optional provider contract checks (`--provider-contract-check`)
    -   optional machine-readable output (`--output-json`)
-   `slideflow build CONFIG_FILE [OPTIONS]`
    -   generate one or many presentations
    -   supports batch params (`--params-path`), dry-run, threads, and RPS controls
    -   optional machine-readable output (`--output-json`)
-   `slideflow doctor [OPTIONS]`
    -   runtime preflight checks (Python/chart/runtime/provider environment)
    -   supports strict fail mode (`--strict`) and JSON output
-   `slideflow templates list|info`
    -   inspect available chart templates and contract metadata
-   `slideflow sheets validate|build|doctor CONFIG_FILE [OPTIONS]`
    -   workbook configuration workflows (`workbook:` schema)
    -   tab-local AI summaries via `workbook.tabs[].ai.summaries[]` (`type: ai_text`)
    -   machine-readable JSON supported via `--output-json`

Examples:

```bash
slideflow doctor --config-file config.yml --registry registry.py --strict --output-json doctor-result.json
slideflow validate config.yml --registry registry.py --provider-contract-check --params-path variants.csv --output-json validate-result.json
slideflow build config.yml --registry registry.py --params-path variants.csv --threads 2 --rps 0.8 --output-json build-result.json
```

For the complete and current command surface, see
[CLI Reference](https://joe-broadhead.github.io/slideflow/cli-reference/).

---

## 📝 Configuration

Your `config.yml` file is the heart of your SlideFlow project. Here\'s a high-level overview of its structure:

```yaml
presentation:
  name: "My Awesome Presentation"
  slides:
    - id: "slide_one_id"
      title: "Title Slide"
      replacements:
        # ... text, table, and AI replacements
      charts:
        # ... chart definitions

provider:
  type: "google_slides" # or "google_docs" or "google_sheets"
  config:
    credentials: "/path/to/your/credentials.json"
    template_id: "your_google_slides_template_id"

citations: # optional
  enabled: true
  mode: "both" # model | execution | both
  location: "document_end" # per_slide | per_section | document_end

template_paths:
  - "./templates"

# For Sheets workflows, use `workbook:` schema and `slideflow sheets ...` commands.
```

For provider-specific behavior, see:

- [Google Sheets Provider](https://joe-broadhead.github.io/slideflow/providers/google-sheets/)
- [Google Slides Provider](https://joe-broadhead.github.io/slideflow/providers/google-slides/)
- [Google Docs Provider](https://joe-broadhead.github.io/slideflow/providers/google-docs/)

---

## 🎨 Customization

SlideFlow is designed to be extensible. You can use your own Python functions for:

-   **Data Transformations:** Clean, reshape, or aggregate your data before it\'s used in charts or replacements.
-   **Custom Formatting:** Format numbers, dates, and other values exactly as you need them.
-   **Custom Charts:** Create unique chart types that are specific to your needs.

To use your own functions, create a `registry.py` file with a `function_registry` dictionary:

```python
# registry.py

def format_as_usd(value):
    return f"${value:,.2f}"

function_registry = {
    "format_as_usd": format_as_usd,
}
```

You can then reference `format_as_usd` in your YAML configuration.

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, local quality gates,
test expectations, and PR checklist.

## 🔒 Dependency Reproducibility Policy

SlideFlow tracks `uv.lock` in git as the canonical lockfile for development and CI.

- CI validates lock freshness with `uv lock --check`.
- Contributor environments should be synced from lock with:

```bash
uv sync --extra dev --extra ai --locked
```

When dependency constraints change in `pyproject.toml`, regenerate `uv.lock` in the
same PR.

---

## 📜 License

MIT License © [Joe Broadhead](https://github.com/joe-broadhead)
