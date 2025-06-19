# Environment Setup

SlideFlow requires a few API credentials to be provided via environment variables.
These variables allow the library to authenticate with external services.

## Google Services

Set `SERVICE_ACCOUNT_PATH` to the path of your Google service account JSON key.
This is used to authenticate with Google Drive and Slides.

```bash
export SERVICE_ACCOUNT_PATH=/path/to/service-account.json
```

## Databricks

The Databricks SQL connector expects the following variables:

- `DATABRICKS_HOST` – the workspace hostname
- `HTTP_PATH` – HTTP path to the SQL warehouse
- `DBT_ACCESS_TOKEN` – personal access token

```bash
export DATABRICKS_HOST="..."
export HTTP_PATH="..."
export DBT_ACCESS_TOKEN="..."
```

## AI Providers

The AI providers rely on their respective API keys:

- `OPENAI_API_KEY` for the OpenAI provider
- `GOOGLE_API_KEY` for the Gemini provider
- `GOOGLE_PROJECT_ID` for Gemini Vertex integration
- `GOOGLE_REGION` for Gemini Vertex integration

```bash
export OPENAI_API_KEY="sk-..."
export GOOGLE_API_KEY="..."
export GOOGLE_PROJECT_ID="my-project-id"
export GOOGLE_REGION="europe-west1"
```

Make sure these environment variables are set before running SlideFlow commands.
