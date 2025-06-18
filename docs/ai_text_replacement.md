# AI Text Replacement

SlideFlow supports generating text placeholders using AI providers. Add a replacement in your YAML config like:

```yaml
- type: ai_text
  placeholder: "{{SUMMARY}}"
  provider: openai
  prompt: "Write a summary for {REGION}"
```
`provider` can be `openai` or `gemini`, or a custom callable registered in your registry file. Additional provider-specific options may be supplied via the optional `provider_args` mapping.

Ensure the relevant API keys (e.g. `OPENAI_API_KEY` or `GOOGLE_API_KEY`) are set in your environment as outlined in the [Environment Setup](environment_setup.md) guide.

You can also load a data source and have the provider summarize that information:

```yaml
- type: ai_text
  placeholder: "{{SUMMARY}}"
  provider: openai
  prompt: "Summarize the quarterly sales data"
  data_source:
    type: csv
    file_path: sales.csv
```

The fetched data is converted to a list of records (list of dictionaries) and
passed to the provider via the `data` argument.
