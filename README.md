# 🚀 SlideFlow

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/release/python-3120/)
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

[Key Features](#-key-features) • [How It Works](#-how-it-works) • [Installation](#-installation) • [Getting Started](#-getting-started) • [CLI Usage](#-cli-usage) • [Configuration](#-configuration) • [Customization](#-customization) • [Contributing](#-contributing)

</div>

---

## ✨ Why SlideFlow?

SlideFlow was built to solve a simple problem: automating the tedious process of creating data-heavy presentations. If you find yourself repeatedly copying and pasting charts and metrics into slide decks, SlideFlow is for you.

-   🎨 **Beautiful, Consistent Visuals:** Leverage the power of Plotly for stunning, replicable charts. Use YAML templates to create a library of reusable chart designs.
-   📊 **Connect Directly to Your Data:** Pull data from CSV files, JSON, Databricks, or even your dbt models. No more manual data exports.
-   ⚡ **Automate Your Reporting:** Stop the manual work. Reduce errors and save time. Your presentations are always up-to-date with your latest data.
-   🚀 **Scale Instantly:** Need to create a presentation for every customer, region, or product? Generate hundreds of personalized presentations at once from a single template.

---

## 🔑 Key Features

-   **Declarative YAML Configuration:** Define your entire presentation in a simple, human/agent readable YAML file.
-   **Multiple Data Source Connectors:**
    -   `csv`: For local CSV files.
    -   `json`: For local JSON files.
    -   `databricks`: For running SQL queries directly against Databricks.
    -   `databricks_dbt`: For using your existing dbt models as data sources.
-   **Dynamic Content Replacements:**
    -   **Text:** Replace simple placeholders like `{{TOTAL_REVENUE}}` with dynamic values.
    -   **Tables:** Populate entire tables in your slides from a DataFrame.
    -   **AI-Generated Text:** Use OpenAI or Gemini to generate summaries, insights, or any other text, right from your data.
-   **Powerful Charting Engine:**
    -   **Plotly Graph Objects:** Create any chart you can imagine with the full power of Plotly.
    -   **YAML Chart Templates:** Define reusable chart styles and configurations.
    -   **Custom Python Functions:** For when you need complete control over your chart generation logic.
-   **Extensible and Customizable:**
    -   Use **Function Registries** to extend SlideFlow with your own Python functions for data transformations, formatting, and more.
-   **Powerful CLI:**
    -   `slideflow build`: Generate one or many presentations.
    -   `slideflow validate`: Validate your configuration before you build.
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
pip install git+https://github.com/joe-broadhead/slideflow.git
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
    -   Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the path of your JSON credentials file or the content of the file itself.

Once you have these, you can run the `build` command:

```bash
slideflow build your_config.yml
```

---

## ⚙️ CLI Usage

SlideFlow comes with a simple CLI.

### `build`

The `build` command generates your presentation(s).

```bash
slideflow build [CONFIG_FILE] [OPTIONS]
```

**Arguments:**

-   `CONFIG_FILE`: Path to your YAML configuration file.

**Options:**

-   `--registry, -r`: Path to a Python file containing a `function_registry`. You can use this option multiple times.
-   `--params-path, -f`: Path to a CSV file containing parameters for generating multiple presentations.
-   `--dry-run`: Validate the configuration without building the presentation.

### `validate`

The `validate` command checks your configuration for errors.

```bash
slideflow validate [CONFIG_FILE] [OPTIONS]
```

**Arguments:**

-   `CONFIG_FILE`: Path to your YAML configuration file.

**Options:**

-   `--registry, -r`: Path to a Python file containing a `function_registry`.

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

## 📜 License

MIT License © [Joe Broadhead](https://github.com/joe-broadhead)

