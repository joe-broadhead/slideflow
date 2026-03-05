# AI Provider Cheatsheet

## OpenAI

```yaml
provider: openai
provider_args:
  model: gpt-4o-mini
  temperature: 0.2
  max_tokens: 256
```

Env contract:

- `OPENAI_API_KEY`

## Gemini

```yaml
provider: gemini
provider_args:
  model: gemini-2.0-flash
  temperature: 0.2
```

Env contract (one typical pattern):

- `GOOGLE_API_KEY`

## Databricks Serving Endpoints

```yaml
provider: databricks
provider_args:
  model: databricks-claude-sonnet-4-6
  base_url: https://<workspace-host>/serving-endpoints
  temperature: 0.2
  max_tokens: 256
```

Env contract:

- `DATABRICKS_TOKEN`

Notes:

- `base_url` should point to the serving-endpoints root, not `/invocations`.
- `model` should be the serving endpoint name.

