import os
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pytest
import yaml  # type: ignore[import-untyped]

from slideflow.presentations.builder import PresentationBuilder
from slideflow.presentations.providers.google_docs import (
    GoogleDocsProvider,
    GoogleDocsProviderConfig,
)

pytestmark = pytest.mark.live_google_docs


def _require_first_env(var_names: Iterable[str], reason: str) -> str:
    for var_name in var_names:
        value = os.getenv(var_name)
        if value:
            return value
    pytest.skip(reason)


def _parse_optional_email_list(var_name: str) -> List[str]:
    raw = os.getenv(var_name, "")
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture(scope="session")
def live_provider() -> GoogleDocsProvider:
    if os.getenv("SLIDEFLOW_RUN_LIVE") != "1":
        pytest.skip("SLIDEFLOW_RUN_LIVE != 1; skipping live Google Docs tests.")

    credentials = _require_first_env(
        ["GOOGLE_DOCS_CREDENTIALS", "GOOGLE_SLIDEFLOW_CREDENTIALS"],
        "GOOGLE_DOCS_CREDENTIALS/GOOGLE_SLIDEFLOW_CREDENTIALS is not set.",
    )
    document_folder_id = _require_first_env(
        ["SLIDEFLOW_LIVE_DOCUMENT_FOLDER_ID", "SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID"],
        "SLIDEFLOW_LIVE_DOCUMENT_FOLDER_ID/SLIDEFLOW_LIVE_PRESENTATION_FOLDER_ID is not set.",
    )
    drive_folder_id = os.getenv("SLIDEFLOW_LIVE_DRIVE_FOLDER_ID", document_folder_id)
    requests_per_second = float(os.getenv("SLIDEFLOW_LIVE_RPS", "1.0"))

    config = GoogleDocsProviderConfig(
        credentials=credentials,
        document_folder_id=document_folder_id,
        drive_folder_id=drive_folder_id,
        strict_cleanup=True,
        requests_per_second=requests_per_second,
    )
    return GoogleDocsProvider(config)


def _extract_document_text(document_payload: Dict[str, Any]) -> str:
    chunks: List[str] = []

    def _walk(elements: List[Any]) -> None:
        for element in elements:
            if not isinstance(element, dict):
                continue

            paragraph = element.get("paragraph")
            if isinstance(paragraph, dict):
                para_elements = paragraph.get("elements", [])
                if isinstance(para_elements, list):
                    for para_element in para_elements:
                        if not isinstance(para_element, dict):
                            continue
                        text_run = para_element.get("textRun")
                        if isinstance(text_run, dict):
                            text_content = text_run.get("content")
                            if isinstance(text_content, str):
                                chunks.append(text_content)

            table = element.get("table")
            if isinstance(table, dict):
                rows = table.get("tableRows", [])
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        cells = row.get("tableCells", [])
                        if isinstance(cells, list):
                            for cell in cells:
                                if not isinstance(cell, dict):
                                    continue
                                content = cell.get("content", [])
                                if isinstance(content, list):
                                    _walk(content)

    body = document_payload.get("body", {})
    if isinstance(body, dict):
        content = body.get("content", [])
        if isinstance(content, list):
            _walk(content)
    return "".join(chunks)


def _count_inline_images(document_payload: Dict[str, Any]) -> int:
    count = 0

    def _walk(elements: List[Any]) -> None:
        nonlocal count
        for element in elements:
            if not isinstance(element, dict):
                continue

            paragraph = element.get("paragraph")
            if isinstance(paragraph, dict):
                para_elements = paragraph.get("elements", [])
                if isinstance(para_elements, list):
                    for para_element in para_elements:
                        if isinstance(para_element, dict) and para_element.get(
                            "inlineObjectElement"
                        ):
                            count += 1

            table = element.get("table")
            if isinstance(table, dict):
                rows = table.get("tableRows", [])
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        cells = row.get("tableCells", [])
                        if isinstance(cells, list):
                            for cell in cells:
                                if not isinstance(cell, dict):
                                    continue
                                content = cell.get("content", [])
                                if isinstance(content, list):
                                    _walk(content)

    body = document_payload.get("body", {})
    if isinstance(body, dict):
        content = body.get("content", [])
        if isinstance(content, list):
            _walk(content)
    return count


def _trash_files(provider: GoogleDocsProvider, file_ids: Iterable[str]) -> None:
    for file_id in file_ids:
        if not file_id:
            continue
        try:
            provider._execute_request(
                provider.drive_service.files().update(
                    fileId=file_id,
                    body={"trashed": True},
                    supportsAllDrives=True,
                )
            )
        except Exception:
            # Cleanup is best-effort in live tests.
            pass


def _create_working_template(provider: GoogleDocsProvider, title_prefix: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    title = f"{title_prefix} template {suffix}"
    base_template_id = os.getenv("SLIDEFLOW_LIVE_DOC_TEMPLATE_ID")
    if base_template_id:
        return provider._copy_template(base_template_id, title)
    return provider.create_presentation(title)


def _overwrite_document(
    provider: GoogleDocsProvider, document_id: str, text: str
) -> None:
    current_doc = provider._execute_request(
        provider.docs_service.documents().get(documentId=document_id)
    )
    end_index = 1
    body = current_doc.get("body", {})
    if isinstance(body, dict):
        content = body.get("content", [])
        if isinstance(content, list):
            for element in content:
                if isinstance(element, dict):
                    element_end = element.get("endIndex")
                    if isinstance(element_end, int):
                        end_index = max(end_index, element_end - 1)

    requests: List[Dict[str, Any]] = []
    if end_index > 1:
        requests.append(
            {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index}}}
        )
    requests.append({"insertText": {"location": {"index": 1}, "text": text}})

    provider._execute_request(
        provider.docs_service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        )
    )


def _write_live_registry(registry_path: Path) -> None:
    registry_path.write_text(
        "def deterministic_ai_provider(prompt: str, label: str = 'LIVE_DOCS_AI', **kwargs) -> str:\n"
        '    return f"{label}: generated summary"\n'
        "\n"
        "function_registry = {\n"
        "    'deterministic_ai_provider': deterministic_ai_provider,\n"
        "}\n",
        encoding="utf-8",
    )


@pytest.mark.live_google_docs
def test_live_google_docs_renders_marker_scoped_replacements_and_inline_chart(
    live_provider: GoogleDocsProvider, tmp_path: Path
):
    created_file_ids: List[str] = []
    share_with = _parse_optional_email_list("SLIDEFLOW_LIVE_SHARE_EMAIL")
    keep_artifacts = _is_truthy(
        os.getenv("SLIDEFLOW_LIVE_KEEP_ARTIFACTS", "1" if share_with else "0")
    )
    share_role = os.getenv("SLIDEFLOW_LIVE_SHARE_ROLE", "reader")

    template_id = _create_working_template(
        live_provider, title_prefix="slideflow-live-docs"
    )
    created_file_ids.append(template_id)

    template_text = (
        "{{SECTION:intro}}\n"
        "{{TITLE_PLACEHOLDER}}\n"
        "{{AI_PLACEHOLDER}}\n"
        "{{TABLE_1,1}} {{TABLE_1,2}}\n\n"
        "{{SECTION:details}}\n"
        "{{DETAILS_PLACEHOLDER}}\n"
    )
    _overwrite_document(live_provider, template_id, template_text)

    data_path = tmp_path / "docs_live_data.csv"
    data_path.write_text(
        "month,revenue\nJan,100\nFeb,120\nMar,140\n",
        encoding="utf-8",
    )

    registry_path = tmp_path / "registry.py"
    _write_live_registry(registry_path)

    provider_config: Dict[str, Any] = {
        "credentials": live_provider.config.credentials,
        "template_id": template_id,
        "document_folder_id": live_provider.config.document_folder_id,
        "drive_folder_id": live_provider.config.drive_folder_id,
        "strict_cleanup": True,
    }
    if share_with:
        provider_config["share_with"] = share_with
        provider_config["share_role"] = share_role

    config_payload = {
        "registry": [registry_path.name],
        "provider": {
            "type": "google_docs",
            "config": provider_config,
        },
        "presentation": {
            "name": f"slideflow docs live {uuid.uuid4().hex[:6]}",
            "slides": [
                {
                    "id": "intro",
                    "charts": [
                        {
                            "type": "plotly_go",
                            "config": {
                                "title": "Live Docs Bar",
                                "x": 20,
                                "y": 20,
                                "width": 320,
                                "height": 180,
                                "data_source": {
                                    "type": "csv",
                                    "name": "docs_live_csv",
                                    "file_path": str(data_path),
                                },
                                "traces": [
                                    {
                                        "type": "bar",
                                        "x": "$month",
                                        "y": "$revenue",
                                    }
                                ],
                            },
                        }
                    ],
                    "replacements": [
                        {
                            "type": "text",
                            "config": {
                                "placeholder": "{{TITLE_PLACEHOLDER}}",
                                "replacement": "Live Docs Title",
                            },
                        },
                        {
                            "type": "ai_text",
                            "config": {
                                "placeholder": "{{AI_PLACEHOLDER}}",
                                "prompt": "Summarize this live docs test run.",
                                "provider": "deterministic_ai_provider",
                                "provider_args": {"label": "LIVE_DOCS_AI"},
                                "data_source": {
                                    "type": "csv",
                                    "name": "docs_live_ai_csv",
                                    "file_path": str(data_path),
                                },
                            },
                        },
                        {
                            "type": "table",
                            "config": {
                                "prefix": "TABLE_",
                                "replacements": {
                                    "{{TABLE_1,1}}": "Metric",
                                    "{{TABLE_1,2}}": "Value",
                                },
                            },
                        },
                    ],
                },
                {
                    "id": "details",
                    "charts": [],
                    "replacements": [
                        {
                            "type": "text",
                            "config": {
                                "placeholder": "{{DETAILS_PLACEHOLDER}}",
                                "replacement": "Details complete",
                            },
                        }
                    ],
                },
            ],
        },
    }

    config_path = tmp_path / "live_google_docs.yml"
    config_path.write_text(
        yaml.safe_dump(config_payload, sort_keys=False),
        encoding="utf-8",
    )

    rendered_document_id = ""
    try:
        presentation = PresentationBuilder.from_yaml(
            yaml_path=config_path,
            registry_paths=[registry_path],
        )
        result = presentation.render()
        rendered_document_id = result.presentation_id
        created_file_ids.append(rendered_document_id)

        if share_with:
            print(
                "Shared rendered document with "
                f"{', '.join(share_with)} ({share_role}): {result.presentation_url}"
            )
        elif keep_artifacts:
            print(
                f"Retained rendered document for inspection: {result.presentation_url}"
            )

        assert result.presentation_url.startswith("https://docs.google.com/document/d/")
        assert result.charts_generated == 1
        assert result.replacements_made >= 5

        rendered_doc = live_provider._execute_request(
            live_provider.docs_service.documents().get(documentId=rendered_document_id)
        )
        rendered_text = _extract_document_text(rendered_doc)

        assert "{{TITLE_PLACEHOLDER}}" not in rendered_text
        assert "{{AI_PLACEHOLDER}}" not in rendered_text
        assert "{{TABLE_1,1}}" not in rendered_text
        assert "{{TABLE_1,2}}" not in rendered_text
        assert "{{DETAILS_PLACEHOLDER}}" not in rendered_text

        assert "Live Docs Title" in rendered_text
        assert "LIVE_DOCS_AI: generated summary" in rendered_text
        assert "Metric" in rendered_text
        assert "Value" in rendered_text
        assert "Details complete" in rendered_text
        assert _count_inline_images(rendered_doc) >= 1
    finally:
        if keep_artifacts:
            print(
                "Retaining live test artifacts (set SLIDEFLOW_LIVE_KEEP_ARTIFACTS=0 for auto-cleanup)."
            )
        else:
            _trash_files(live_provider, created_file_ids)
