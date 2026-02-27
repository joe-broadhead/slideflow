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

**SlideFlow is a Python-based tool for generating beautiful, data-driven presentations directly from your data sources.**

[Key Features](#-key-features) • [How It Works](#-how-it-works) • [Installation](#-installation) • [Getting Started](#-getting-started) • [CLI Usage](#-cli-usage) • [Configuration](#-configuration) • [Customization](#-customization) • [Contributing](CONTRIBUTING.md)

</div>

---

## ✨ Why SlideFlow?

SlideFlow was built to solve a simple problem: automating the tedious process of creating data-heavy presentations. If you find yourself repeatedly copying and pasting charts and metrics into slide decks, SlideFlow is for you.

-   🎨 **Beautiful, Consistent Visuals:** Leverage the power of Plotly for stunning, replicable charts. Use YAML templates to create a library of reusable chart designs.
-   📊 **Connect Directly to Your Data:** Pull data from CSV files, JSON, Databricks, or even your dbt models. No more manual data exports.
-   ⚡ **Automate Your Reporting:** Stop the manual work. Reduce errors and save time. Your presentations are always up-to-date with your latest data.
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
    -   `slideflow templates`: Inspect available template names and parameter contracts.
    -   Generate multiple presentations from a single template using a CSV parameter file.

---

## 🔧 How It Works

SlideFlow works in three simple steps:

1.  **Define:** You create a YAML file that defines your presentation. This includes the Google Slides template to use, the data sources to connect to, and the content for each slide (text, charts, etc.).
2.  **Connect & Transform:** SlideFlow connects to your specified data sources, fetches the data, and applies any transformations you\'ve defined.
3.  **Build:** SlideFlow creates a new presentation, populates it with your data and charts, and saves it to your Google Drive.

---

## 🛠 Installation

```bash
pip install slideflow-presentations
```

---

## 🧑‍💻 Getting Started

To create your first presentation, you\'ll need:

1.  **A Google Slides Template:** Create a Google Slides presentation with the layout and branding you want. Note the ID of each slide you want to populate.
2.  **Your Data:** Have your data ready in a CSV file, or have your Databricks credentials configured.
3.  **A YAML Configuration File:** This is where you\'ll define your presentation. See the [Configuration](#-configuration) section for more details.
4.  **Google Cloud Credentials:** You'll need a Google Cloud service account with access to the Google Slides and Google Drive APIs. Provide your credentials in one of the following ways:

    -   Set the `credentials` field in your `config.yml` to the path of your JSON credentials file.
    -   Set the `credentials` field in your `config.yml` to the JSON content of your credentials file as a string.
    -   Set the `GOOGLE_SLIDEFLOW_CREDENTIALS` environment variable to the path of your JSON credentials file or the content of the file itself.

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
  type: "google_slides"
  config:
    credentials: "/path/to/your/credentials.json"
    template_id: "your_google_slides_template_id"

template_paths:
  - "./templates"
```

For more detailed information on the configuration options, please see the documentation.

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
