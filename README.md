# 🚀 SlideFlow

```
  ____  _ _     _       __ _                
 / ___|| (_) __| | ___ / _| | _____      __ 
 \___ \| | |/ _` |/ _ \ |_| |/ _ \ \ /\ / / 
  ___) | | | (_| |  __/  _| | (_) \ V  V /  
 |____/|_|_|\__,_|\___|_| |_|\___/ \_/\_/   

         SlideFlow
     Beautiful slides.
       Direct from your data.
```

SlideFlow streams your insights into Google Slides presentations effortlessly.

---

## ✨ Why SlideFlow?

- 🎨 **Beautiful visuals.** Powered by Plotly.
- 📊 **Direct from your data sources.** CSV, Pandas, SQL Warehouses, DBT.
- ⚡ **Automate reports.** No manual work, fewer errors.
- 🚀 **Scale instantly.** Generate hundreds of presentations at once.

SlideFlow lets you focus on insights, not slide decks.

---

## 🛠 Installation

```bash
pip install git+https://github.com/joe-broadhead/slideflow.git@v0.0.0
```
---

## 🧑‍💻 Quick Start

Define your presentation with a simple YAML:

```yaml
name: "Weekly Report - {{REGION}}"
template_id: your-google-template-id
slides:
  - slide_id: g123456
    charts:
      - name: Sales by Store
        chart_function: bar
        x_col: sales
        y_col: store_name
        data_source:
          type: csv
          file_path: "data/sales.csv"
    replacements:
      - type: text
        placeholder: "{{REGION}}"
        replacement: "Asia"
```

Generate your slides:

```bash
slideflow build config.yml
```

Bulk create presentations:

```bash
slideflow build-bulk run config.yml --param-file params.csv
```

---

## 🌟 Key Features

- 📈 **Rich Plotly visualizations**
- 🗂 **Easy integration** with CSV, pandas, Databricks, and dbt
- 🎯 **Fully customizable** charts and slide templates
- 🛠 **Simple YAML configs** for clarity
- ⚙️ **Parallel generation** for scale

---

## 📖 Getting Started

All you need is:

1. A Google Slides template
2. Your data (CSV, Databricks, DBT)
3. A YAML config file

SlideFlow does the rest.

---

## 📜 License

MIT License © [Joe Broadhead](https://github.com/joe-broadhead)

---