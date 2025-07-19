# Quickstart Example

This guide will walk you through running the quickstart example.

## 1. Prerequisites

Before you begin, make sure you have followed the steps in the [Getting Started](getting-started.md) guide to install SlideFlow and set up your Google Cloud credentials.

## 2. Download the Quickstart Files

The quickstart files are located in the `docs/quickstart` directory of the SlideFlow repository. You will need:

-   `config.yml`: The configuration file for the quickstart presentation.
-   `data.csv`: The sample data for the presentation.
-   `bar_chart.yml`: A template for a reusable bar chart.
-   `registry.py`: An empty registry file.

## 3. Create a Google Slides Template

Create a new Google Slides presentation to use as a template. In this template, you will need:

-   Two slides. The `config.yml` file uses the example IDs `g1_0_0` and `g1_0_1`. You will need to replace these with the actual IDs of the slides in your template. The first slide should have a text box with the placeholder `{{MONTH}}`.

Once you have created the template, copy its ID from the URL in your browser.

## 4. Update the Configuration

Open the `config.yml` file and make the following changes:

-   Replace `your_google_slides_template_id` with the ID of your Google Slides template.
-   Replace `/path/to/your/credentials.json` with the path to your Google Cloud service account credentials file.

## 5. Run the Quickstart

Now you are ready to run the quickstart. From your terminal, run the following command:

```bash
slideflow build docs/quickstart/config.yml --registry docs/quickstart/registry.py
```

SlideFlow will generate a new presentation in your Google Drive with two slides. The first slide will contain a bar chart of the monthly revenue, and the second slide will contain a bar chart of the monthly active users, generated from the `bar_chart.yml` template.
