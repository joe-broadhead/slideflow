# AI Providers

SlideFlow's `ai_text` replacement can generate text with AI providers.
Built-in provider names are:

- `openai`
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
- invalid model/provider combination
- upstream rate limits
- data transform failures before provider call

Use `slideflow validate` for config/function wiring and runtime logs for provider/API errors.
