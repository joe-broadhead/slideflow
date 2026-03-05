# AI Providers

SlideFlow's `ai_text` replacement can generate text with AI providers.
Built-in provider names are:

- `openai`
- `databricks`
- `gemini`

You can also supply a provider class, provider instance, or plain callable.

## `ai_text` Config Shape

```yaml
- type: "ai_text"
  config:
    placeholder: "{{SUMMARY}}"
    prompt: "Summarize the key findings."
    provider: "openai"
    provider_args:
      model: "gpt-4o"
      temperature: 0.2
    data_source:
      type: "csv"
      name: "summary_data"
      file_path: "./data/summary.csv"
```

`data_source` may be a single source or a list of sources.

## OpenAI Provider

Runtime requirement:

```bash
export OPENAI_API_KEY="<key>"
```

Typical args in `provider_args`:

- `model`
- `temperature`
- `max_tokens`
- `top_p`
- `frequency_penalty`
- `presence_penalty`

## Databricks Provider

Runtime requirement:

```bash
export DATABRICKS_TOKEN="<token>"
export DATABRICKS_SERVING_BASE_URL="https://<DATABRICKS_HOST>/serving-endpoints"
```

Typical `provider_args`:

- `model` (serving endpoint name, required)
- `max_tokens`
- `temperature`
- `top_p`
- `stop`
- `response_format`

Supported optional text-generation args:

- `frequency_penalty`
- `presence_penalty`
- `reasoning_effort`

Text-only guardrails:

- SlideFlow's Databricks provider blocks tool-calling and streaming args in
  `ai_text` mode (`tools`, `tool_choice`, `stream`, `n`, `logprobs`, `top_logprobs`).

Example:

```yaml
- type: "ai_text"
  config:
    placeholder: "{{SUMMARY}}"
    prompt: "Summarize this week's results in three bullets."
    provider: "databricks"
    provider_args:
      model: "<SERVING_ENDPOINT_NAME>"
      base_url: "https://<DATABRICKS_HOST>/serving-endpoints"
      max_tokens: 256
      temperature: 0.2
      top_p: 0.95
```

## Gemini Provider

### Gemini API mode (non-Vertex)

Set one of:

```bash
export GOOGLE_API_KEY="<key>"
# or
export GEMINI_API_KEY="<key>"
```

### Vertex AI mode

Set provider arguments:

```yaml
provider: "gemini"
provider_args:
  vertex: true
  project: "my-gcp-project"
  location: "us-central1"
  model: "gemini-pro"
```

Credentials can be provided via `provider_args.credentials` (path or raw JSON) or `GOOGLE_SLIDEFLOW_CREDENTIALS`.

## Provider Argument Routing

When `provider` is a class or registered provider name, SlideFlow splits `provider_args` into:

- constructor args (`__init__`)
- generation-call args (`generate_text`)

This lets you keep all AI settings in one place.

## Request Identification

For observability/auditing, SlideFlow tags built-in AI provider HTTP requests
with a `User-Agent` identifier of `Slideflow`:

- OpenAI provider
- Databricks provider (serving-endpoints mode)
- Gemini provider (API and Vertex modes)

## Custom Provider Options

### Option 1: callable function

```python
def deterministic_ai_provider(prompt: str, label: str = "AI", **kwargs) -> str:
    return f"{label}: {prompt[:40]}..."

function_registry = {
    "deterministic_ai_provider": deterministic_ai_provider,
}
```

```yaml
provider: "deterministic_ai_provider"
provider_args:
  label: "LIVE_AI"
```

### Option 2: custom provider class

Register class providers through the AI registry APIs when you need reusable provider implementations.

## Data Context Behavior

When data is supplied, SlideFlow appends structured records to the prompt in this form:

- `Data from <source_name>: <records>`

Data transforms run before prompt injection, so you can filter/aggregate context first.

## Failure Modes

Common failures:

- missing API credentials (`OPENAI_API_KEY`, `GOOGLE_API_KEY`, etc.)
- missing Databricks runtime settings (`DATABRICKS_TOKEN`, Databricks base URL)
- invalid model/provider combination
- upstream rate limits
- data transform failures before provider call

Use `slideflow validate` for config/function wiring and runtime logs for provider/API errors.
