# 🧑‍💻 Getting Started

This guide will walk you through the process of creating your first presentation with SlideFlow.

## 1. Installation

First, install SlideFlow using pip:

```bash
pip install git+https://github.com/joe-broadhead/slideflow.git
```

## 2. Prerequisites

Before you can generate a presentation, you'll need a few things:

-   **A Google Slides Template:** Create a Google Slides presentation that will serve as your template. This should have the layout, branding, and placeholder text that you want to use. For each slide that you want to populate, you'll need to know its ID. You can find the slide ID in the URL of the Google Slides editor. For example, in the URL `https://docs.google.com/presentation/d/1-I-fJUtl1zNOOw_r9pJ9J0WqyZIqZ2eznIw3Og__Kew/edit#slide=id.g1_0_0`, the slide ID is `g1_0_0`.
-   **Your Data:** Have your data ready. This can be a local CSV or JSON file, or you can connect directly to a Databricks SQL warehouse or a dbt project.
-   **Google Cloud Credentials:** You'll need a Google Cloud service account with the following APIs enabled:
    -   Google Slides API
    -   Google Drive API

    Create a service account, download the JSON credentials file, and save it to your local machine. You'll need the path to this file for your configuration.

## 3. Create Your Configuration File

Create a YAML file (e.g., `config.yml`) to define your presentation. This file is the heart of your SlideFlow project. Here's a simple example:

```yaml
presentation:
  name: "My First SlideFlow Presentation"
  slides:
    - id: "g1_0_0"
      title: "Title Slide"
      replacements:
        - type: "text"
          config:
            placeholder: "{{TITLE}}"
            replacement: "Hello, SlideFlow!"

provider:
  type: "google_slides"
  config:
    credentials_path: "/path/to/your/credentials.json"
    template_id: "your_google_slides_template_id"
```

## 4. Validate Your Configuration

Before building your presentation, it's a good practice to validate your configuration file. This will check for any errors in your YAML structure or data source connections.

```bash
slideflow validate config.yml
```

If the validation is successful, you're ready to build your presentation.

## 5. Build Your Presentation

Now, you can build your presentation using the SlideFlow CLI:

```bash
slideflow build config.yml
```

SlideFlow will connect to your data sources, generate your charts, and create a new presentation in your Google Drive.

## 6. Next Steps

Checkout the [Quickstart](quickstart.md)