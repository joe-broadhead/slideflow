# 🚀 Welcome to SlideFlow

<div align="center">

**SlideFlow is a Python-based tool for generating beautiful, data-driven presentations directly from your data sources.**

</div>

---

## ✨ Why SlideFlow?

SlideFlow was built to solve a simple problem: automating the tedious process of creating data-heavy presentations. If you find yourself repeatedly copying and pasting charts and metrics into slide decks, SlideFlow is for you.

-	🎨 **Beautiful, Consistent Visuals:** Leverage the power of Plotly for stunning, replicable charts. Use YAML templates to create a library of reusable chart designs.
-	📊 **Connect Directly to Your Data:** Pull data from CSV files, JSON, Databricks, or even your dbt models. No more manual data exports.
-	⚡ **Automate Your Reporting:** Stop the manual work. Reduce errors and save time. Your presentations are always up-to-date with your latest data.
-	🚀 **Scale Instantly:** Need to create a presentation for every customer, region, or product? Generate hundreds of personalized presentations at once from a single template.

---

## 🔑 Key Features

-	**Declarative YAML Configuration:** Define your entire presentation in a simple, human-readable YAML file.
-	**Multiple Data Source Connectors:**
	-	`csv`: For local CSV files.
	-	`json`: For local JSON files.
	-	`databricks`: For running SQL queries directly against Databricks.
	-	`databricks_dbt`: For using your existing dbt models as data sources.
-	**Dynamic Content Replacements:**
	-	**Text:** Replace simple placeholders like `{{TOTAL_REVENUE}}` with dynamic values.
	-	**Tables:** Populate entire tables in your slides from a DataFrame.
	-	**AI-Generated Text:** Use OpenAI or Gemini to generate summaries, insights, or any other text, right from your data.
-	**Powerful Charting Engine:**
	-	**Plotly Graph Objects:** Create any chart you can imagine with the full power of Plotly.
	-	**YAML Chart Templates:** Define reusable chart styles and configurations.
	-	**Custom Python Functions:** For when you need complete control over your chart generation logic.
-	**Extensible and Customizable:**
	-	Use **Function Registries** to extend SlideFlow with your own Python functions for data transformations, formatting, and more.
-	**Powerful CLI:**
	-	`slideflow build`: Generate one or many presentations.
	-	`slideflow validate`: Validate your configuration before you build.
	-	Generate multiple presentations from a single template using a CSV parameter file.

---

## 🔧 How It Works

SlideFlow works in three simple steps:

1.	**Define:** You create a YAML file that defines your presentation. This includes the Google Slides template to use, the data sources to connect to, and the content for each slide (text, charts, etc.).
2.	**Connect & Transform:** SlideFlow connects to your specified data sources, fetches the data, and applies any transformations you've defined.
3.	**Build:** SlideFlow creates a new presentation, populates it with your data and charts, and saves it to your Google Drive.