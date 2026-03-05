from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

import slideflow.presentations.providers.factory as provider_factory_module
import slideflow.presentations.providers.google_docs as google_docs_module
from slideflow.constants import Environment
from slideflow.presentations.config import ProviderConfig
from slideflow.utilities.exceptions import AuthenticationError, RenderingError


def _provider_without_init() -> google_docs_module.GoogleDocsProvider:
    provider = object.__new__(google_docs_module.GoogleDocsProvider)
    provider._section_insert_indices = {}
    return provider


def _attach_default_docs_config(
    provider: google_docs_module.GoogleDocsProvider,
) -> None:
    provider.config = SimpleNamespace(
        section_marker_prefix="{{SECTION:",
        section_marker_suffix="}}",
        remove_section_markers=False,
        strict_cleanup=False,
    )


def _http_error(
    message: str, status: Optional[int] = None, content: Optional[bytes] = None
):
    error = google_docs_module.HttpError(message)
    if status is not None:
        error.resp = SimpleNamespace(status=status)
    if content is not None:
        error.content = content
    return error


def _document_from_paragraph_run_groups(
    *paragraph_run_groups: Tuple[str, ...],
) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = []
    cursor = 1
    for paragraph_runs in paragraph_run_groups:
        paragraph_start = cursor
        paragraph_elements: List[Dict[str, Any]] = []
        for run_text in paragraph_runs:
            start_index = cursor
            end_index = cursor + _utf16_units(run_text)
            paragraph_elements.append(
                {
                    "startIndex": start_index,
                    "endIndex": end_index,
                    "textRun": {"content": run_text},
                }
            )
            cursor = end_index
        paragraph_end = cursor
        content.append(
            {
                "startIndex": paragraph_start,
                "endIndex": paragraph_end,
                "paragraph": {"elements": paragraph_elements},
            }
        )
    return {"body": {"content": content}}


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _document_from_paragraph_texts(*paragraph_texts: str) -> Dict[str, Any]:
    return _document_from_paragraph_run_groups(
        *[(paragraph_text,) for paragraph_text in paragraph_texts]
    )


def _append_toc_copy(document: Dict[str, Any], toc_text: str) -> Dict[str, Any]:
    body = document.setdefault("body", {})
    content = body.setdefault("content", [])
    if not isinstance(content, list):
        return document

    cursor = 1
    if content:
        last = content[-1]
        if isinstance(last, dict):
            last_end = last.get("endIndex")
            if isinstance(last_end, int):
                cursor = last_end

    toc_start = cursor
    toc_end = toc_start + _utf16_units(toc_text)
    toc_content = [
        {
            "startIndex": toc_start,
            "endIndex": toc_end,
            "paragraph": {
                "elements": [
                    {
                        "startIndex": toc_start,
                        "endIndex": toc_end,
                        "textRun": {"content": toc_text},
                    }
                ]
            },
        }
    ]
    content.append(
        {
            "startIndex": toc_start,
            "endIndex": toc_end,
            "tableOfContents": {"content": toc_content},
        }
    )
    return document


def test_google_docs_provider_init_success(monkeypatch):
    captured: Dict[str, Any] = {}

    def _handle_credentials(_credentials, env_var_names=None):
        captured["env_var_names"] = list(env_var_names or [])
        return {"client_email": "svc@example.com"}

    monkeypatch.setattr(
        google_docs_module,
        "handle_google_credentials",
        _handle_credentials,
    )
    monkeypatch.setattr(
        google_docs_module.Credentials,
        "from_service_account_info",
        lambda info, scopes: captured.update({"info": info, "scopes": scopes})
        or "creds",
    )

    def _fake_build(service, version, credentials, **kwargs):
        captured.setdefault("build_calls", []).append(
            {
                "service": service,
                "version": version,
                "credentials": credentials,
                "kwargs": kwargs,
            }
        )
        return f"{service}:{version}:{credentials}"

    monkeypatch.setattr(google_docs_module, "build", _fake_build)
    monkeypatch.setattr(
        google_docs_module, "_get_rate_limiter", lambda rps: f"rl:{rps}"
    )

    provider = google_docs_module.GoogleDocsProvider(
        google_docs_module.GoogleDocsProviderConfig(
            credentials='{"type":"service_account"}', requests_per_second=2.0
        )
    )

    assert provider.docs_service == "docs:v1:creds"
    assert provider.drive_service == "drive:v3:creds"
    assert provider.rate_limiter == "rl:2.0"
    assert captured["info"] == {"client_email": "svc@example.com"}
    assert captured["scopes"] == google_docs_module.GoogleDocsProvider.SCOPES
    assert captured["env_var_names"] == [
        Environment.GOOGLE_DOCS_CREDENTIALS,
        Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
    ]
    assert len(captured["build_calls"]) == 2
    assert all(
        callable(call["kwargs"].get("requestBuilder"))
        for call in captured["build_calls"]
    )


def test_google_docs_provider_init_authentication_failure(monkeypatch):
    monkeypatch.setattr(
        google_docs_module,
        "handle_google_credentials",
        lambda _credentials, env_var_names=None: {"invalid": True},
    )
    monkeypatch.setattr(
        google_docs_module.Credentials,
        "from_service_account_info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad creds")),
    )

    with pytest.raises(AuthenticationError, match="Credentials authentication failed"):
        google_docs_module.GoogleDocsProvider(
            google_docs_module.GoogleDocsProviderConfig(credentials='{"invalid":true}')
        )


def test_google_docs_config_validates_transfer_ownership_target():
    with pytest.raises(ValueError, match="transfer_ownership_to"):
        google_docs_module.GoogleDocsProviderConfig(
            transfer_ownership_to="not-an-email"
        )

    config = google_docs_module.GoogleDocsProviderConfig(
        transfer_ownership_to=" owner@example.com "
    )
    assert config.transfer_ownership_to == "owner@example.com"


def test_google_docs_provider_factory_registration():
    config = ProviderConfig(
        type="google_docs",
        config={"credentials": '{"type":"service_account"}'},
    )
    provider = provider_factory_module.ProviderFactory.create_provider(config)

    assert isinstance(provider, google_docs_module.GoogleDocsProvider)
    assert (
        "google_docs"
        in provider_factory_module.ProviderFactory.get_available_providers()
    )


def test_run_preflight_checks_without_credentials(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(credentials=None, requests_per_second=1.0)
    provider.docs_service = None
    provider.drive_service = None
    provider.rate_limiter = None
    monkeypatch.delenv(Environment.GOOGLE_DOCS_CREDENTIALS, raising=False)
    monkeypatch.delenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, raising=False)

    checks = provider.run_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}
    assert check_map["google_docs_credentials_present"] is False
    assert check_map["docs_service_initialized"] is False
    assert check_map["drive_service_initialized"] is False
    assert check_map["rate_limiter_initialized"] is False


def test_run_preflight_checks_validates_transfer_target(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        credentials=None,
        requests_per_second=1.0,
        transfer_ownership_to="bad-target",
    )
    provider.docs_service = object()
    provider.drive_service = object()
    provider.rate_limiter = object()
    monkeypatch.delenv(Environment.GOOGLE_DOCS_CREDENTIALS, raising=False)
    monkeypatch.delenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, raising=False)

    checks = provider.run_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}

    assert check_map["ownership_transfer_target_valid"] is False


def test_create_presentation_template_and_plain(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(template_id="template-1")

    copy_calls: List[Tuple[str, str]] = []
    create_calls: List[str] = []
    monkeypatch.setattr(
        provider, "_copy_template", lambda t, n: copy_calls.append((t, n)) or "copied"
    )
    monkeypatch.setattr(
        provider, "_create_document", lambda n: create_calls.append(n) or "created"
    )

    assert provider.create_presentation("Doc A") == "copied"
    assert copy_calls == [("template-1", "Doc A")]

    assert provider.create_presentation("Doc B", template_id="template-2") == "copied"
    assert copy_calls[-1] == ("template-2", "Doc B")

    provider.config = SimpleNamespace(template_id=None)
    assert provider.create_presentation("Doc C") == "created"
    assert create_calls == ["Doc C"]


def test_transfer_presentation_ownership_success_and_shared_drive_guard():
    provider = _provider_without_init()
    created_permissions: List[Dict[str, Any]] = []

    class _Files:
        def get(self, **kwargs):
            return ("files-get", kwargs)

    class _Permissions:
        def create(self, **kwargs):
            created_permissions.append(kwargs)
            return ("permissions-create", kwargs)

    provider.drive_service = SimpleNamespace(
        files=lambda: _Files(),
        permissions=lambda: _Permissions(),
    )

    def _exec(request):
        if request[0] == "files-get":
            return {"id": "doc-1"}
        return {}

    provider._execute_request = _exec
    provider.transfer_presentation_ownership("doc-1", "owner@example.com")

    assert created_permissions == [
        {
            "fileId": "doc-1",
            "body": {
                "type": "user",
                "role": "owner",
                "emailAddress": "owner@example.com",
            },
            "transferOwnership": True,
            "sendNotificationEmail": True,
            "supportsAllDrives": False,
        }
    ]

    provider._execute_request = lambda request: (
        {"id": "doc-2", "driveId": "drive-123"} if request[0] == "files-get" else {}
    )
    with pytest.raises(ValueError, match="Shared Drives"):
        provider.transfer_presentation_ownership("doc-2", "owner@example.com")


def test_insert_chart_and_replace_text_requests():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )
    section_one = "{{SECTION:section-1}} Alpha {{PLACEHOLDER}}\n"
    section_two = "{{SECTION:section-2}} Beta {{PLACEHOLDER}}\n"
    mock_document = _document_from_paragraph_texts(section_one, section_two)

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return mock_document
        if request[0] == "batch-update":
            return {}
        return {}

    provider._execute_request = _exec

    provider.insert_chart_to_slide(
        "doc-1", "section-1", "https://img.example/chart.png", 10, 20, 300, 200
    )
    assert requests[0][0] == "doc-get"
    assert requests[1][0] == "batch-update"
    insert_payload = requests[1][1]["body"]["requests"][0]["insertInlineImage"]
    assert insert_payload["uri"] == "https://img.example/chart.png"
    expected_index = 1 + len("{{SECTION:section-1}}")
    assert insert_payload["location"]["index"] == expected_index
    assert "endOfSegmentLocation" not in insert_payload

    replaced = provider.replace_text_in_slide(
        "doc-1", "section-1", "{{PLACEHOLDER}}", "VALUE"
    )
    assert replaced == 1
    replace_requests = requests[3][1]["body"]["requests"]
    assert len(replace_requests) == 2
    delete_range = replace_requests[0]["deleteContentRange"]["range"]
    assert delete_range["startIndex"] >= expected_index
    section_two_start = 1 + len(section_one)
    assert delete_range["startIndex"] < section_two_start


def test_insert_chart_preserves_chart_order_within_same_section():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )
    mock_document = _document_from_paragraph_texts("{{SECTION:section-1}} Alpha\n")

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return mock_document
        return {}

    provider._execute_request = _exec

    provider.insert_chart_to_slide(
        "doc-1", "section-1", "https://img.example/chart1.png", 0, 0, 300, 200
    )
    provider.insert_chart_to_slide(
        "doc-1", "section-1", "https://img.example/chart2.png", 0, 0, 300, 200
    )

    first_insert = requests[1][1]["body"]["requests"][0]["insertInlineImage"]
    second_insert = requests[3][1]["body"]["requests"][0]["insertInlineImage"]
    assert second_insert["location"]["index"] == first_insert["location"]["index"] + 1


def test_insert_chart_warns_when_position_values_are_ignored(monkeypatch):
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return _document_from_paragraph_texts("{{SECTION:section-1}} Alpha\n")
        return {}

    warning_messages: List[str] = []
    monkeypatch.setattr(
        google_docs_module.logger,
        "warning",
        lambda message, *args: warning_messages.append(message % args),
    )

    provider._execute_request = _exec
    provider.insert_chart_to_slide(
        "doc-1", "section-1", "https://img.example/chart.png", 10, 20, 300, 200
    )

    assert requests[0][0] == "doc-get"
    assert requests[1][0] == "batch-update"
    assert len(warning_messages) == 1
    assert "ignores chart positioning values" in warning_messages[0]
    assert "section-1" in warning_messages[0]


def test_insert_chart_raises_when_marker_missing():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return _document_from_paragraph_texts("{{SECTION:section-1}} Alpha\n")
        return {}

    provider._execute_request = _exec

    with pytest.raises(RenderingError, match="Missing section marker"):
        provider.insert_chart_to_slide(
            "doc-2", "missing", "https://img.example/chart.png", 10, 20, 300, 200
        )


def test_replace_text_raises_when_markers_are_duplicated():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )

    provider._execute_request = lambda request: (
        _document_from_paragraph_texts(
            "{{SECTION:section-1}} First\n",
            "{{SECTION:section-1}} Second\n",
        )
        if request[0] == "doc-get"
        else {}
    )

    with pytest.raises(RenderingError, match="Duplicate section markers"):
        provider.replace_text_in_slide("doc-1", "section-1", "{{PLACEHOLDER}}", "VALUE")


def test_replace_text_handles_utf16_indices_with_emoji():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )
    section_one = "{{SECTION:section-1}} 🙂 {{PLACEHOLDER}}\n"
    section_two = "{{SECTION:section-2}} Tail\n"
    mock_document = _document_from_paragraph_texts(section_one, section_two)

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return mock_document
        return {}

    provider._execute_request = _exec

    replaced = provider.replace_text_in_slide(
        "doc-emoji", "section-1", "{{PLACEHOLDER}}", "VALUE"
    )
    assert replaced == 1
    replace_requests = requests[1][1]["body"]["requests"]
    delete_range = replace_requests[0]["deleteContentRange"]["range"]
    expected_start = 1 + _utf16_units("{{SECTION:section-1}} 🙂 ")
    expected_end = expected_start + _utf16_units("{{PLACEHOLDER}}")
    assert delete_range["startIndex"] == expected_start
    assert delete_range["endIndex"] == expected_end
    insert_payload = replace_requests[1]["insertText"]
    assert insert_payload["location"]["index"] == expected_start


def test_marker_detection_handles_adjacent_text_runs():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )
    mock_document = _document_from_paragraph_run_groups(
        ("{{SECTION:", "section-1}} Alpha {{PLACEHOLDER}}\n"),
        ("{{SECTION:section-2}} Tail\n",),
    )

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return mock_document
        return {}

    provider._execute_request = _exec

    provider.insert_chart_to_slide(
        "doc-split", "section-1", "https://img.example/chart.png", 10, 20, 300, 200
    )
    insert_payload = requests[1][1]["body"]["requests"][0]["insertInlineImage"]
    assert insert_payload["location"]["index"] == 1 + _utf16_units(
        "{{SECTION:section-1}}"
    )

    replaced = provider.replace_text_in_slide(
        "doc-split", "section-1", "{{PLACEHOLDER}}", "VALUE"
    )
    assert replaced == 1


def test_marker_resolution_ignores_table_of_contents_copies():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )
    mock_document = _document_from_paragraph_texts(
        "{{SECTION:section-1}} Alpha {{PLACEHOLDER}}\n",
        "{{SECTION:section-2}} Tail\n",
    )
    _append_toc_copy(mock_document, "{{SECTION:section-1}}")

    provider._execute_request = lambda request: (
        mock_document if request[0] == "doc-get" else {}
    )

    replaced = provider.replace_text_in_slide(
        "doc-toc", "section-1", "{{PLACEHOLDER}}", "VALUE"
    )
    assert replaced == 1


def test_remove_section_markers_deletes_body_markers_only():
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs),
            get=lambda **kwargs: ("doc-get", kwargs),
        )
    )
    mock_document = _document_from_paragraph_texts(
        "{{SECTION:section-1}} Intro\n",
        "{{SECTION:section-2}} Details\n",
    )
    _append_toc_copy(mock_document, "{{SECTION:section-1}}")

    requests: List[Any] = []

    def _exec(request: Any) -> Any:
        requests.append(request)
        if request[0] == "doc-get":
            return mock_document
        return {}

    provider._execute_request = _exec

    removed = provider._remove_section_markers("doc-remove")

    assert removed == 2
    assert requests[0][0] == "doc-get"
    assert requests[1][0] == "batch-update"
    delete_requests = requests[1][1]["body"]["requests"]
    assert len(delete_requests) == 2
    first_range = delete_requests[0]["deleteContentRange"]["range"]
    second_range = delete_requests[1]["deleteContentRange"]["range"]
    assert first_range["startIndex"] > second_range["startIndex"]


def test_finalize_presentation_skips_marker_cleanup_when_disabled(monkeypatch):
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.config.remove_section_markers = False

    calls: List[str] = []
    monkeypatch.setattr(
        provider,
        "_remove_section_markers",
        lambda document_id: calls.append(document_id) or 0,
    )

    provider.finalize_presentation("doc-no-cleanup")
    assert calls == []


def test_finalize_presentation_runs_marker_cleanup_when_enabled(monkeypatch):
    provider = _provider_without_init()
    _attach_default_docs_config(provider)
    provider.config.remove_section_markers = True

    calls: List[str] = []
    monkeypatch.setattr(
        provider,
        "_remove_section_markers",
        lambda document_id: calls.append(document_id) or 2,
    )

    provider.finalize_presentation("doc-cleanup")
    assert calls == ["doc-cleanup"]


def test_upload_share_and_delete_paths():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        drive_folder_id="folder-1",
        strict_cleanup=False,
        chart_image_sharing_mode="public",
    )

    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(
            create=lambda **kwargs: ("files-create", kwargs),
            update=lambda **kwargs: ("files-update", kwargs),
            copy=lambda **kwargs: ("files-copy", kwargs),
            get=lambda **kwargs: ("files-get", kwargs),
        ),
        permissions=lambda: SimpleNamespace(
            create=lambda **kwargs: ("perm-create", kwargs)
        ),
    )

    calls: List[Any] = []

    def _exec(request):
        calls.append(request)
        if request[0] == "files-create":
            return {"id": "file-1"}
        if request[0] == "files-copy":
            return {"id": "doc-from-template"}
        if request[0] == "files-get":
            return {"parents": ["old-parent"]}
        return {}

    provider._execute_request = _exec

    url, file_id = provider.upload_chart_image("doc-1", b"bytes", "chart.png")
    assert url == "https://drive.google.com/uc?id=file-1"
    assert file_id == "file-1"

    provider.share_presentation("doc-1", ["a@example.com", "b@example.com"], "reader")
    assert len([call for call in calls if call[0] == "perm-create"]) == 3

    provider.config.document_folder_id = "docs-folder"
    copied_id = provider._copy_template("template-123", "Newsletter")
    assert copied_id == "doc-from-template"

    provider._move_file_to_folder("doc-1", "new-folder")
    update_calls = [call for call in calls if call[0] == "files-update"]
    assert update_calls

    provider.delete_chart_image("file-1")

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("forbidden", status=403)
    )
    provider.delete_chart_image("file-2")


def test_upload_chart_image_waits_for_drive_acl_propagation(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        drive_folder_id="folder-1",
        strict_cleanup=False,
        chart_image_sharing_mode="public",
    )
    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(create=lambda **kwargs: ("files-create", kwargs)),
        permissions=lambda: SimpleNamespace(
            create=lambda **kwargs: ("perm-create", kwargs)
        ),
    )

    calls: List[Any] = []

    def _exec(request):
        calls.append(request)
        if request[0] == "files-create":
            return {"id": "file-1"}
        return {}

    sleep_calls: List[float] = []
    monkeypatch.setattr(
        google_docs_module, "time", SimpleNamespace(sleep=sleep_calls.append)
    )
    monkeypatch.setattr(
        google_docs_module.Timing,
        "GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S",
        1.5,
    )

    provider._execute_request = _exec

    url, file_id = provider.upload_chart_image("doc-1", b"bytes", "chart.png")
    assert url == "https://drive.google.com/uc?id=file-1"
    assert file_id == "file-1"
    assert sleep_calls == [1.5]


def test_upload_chart_image_restricted_mode_skips_public_permission(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        drive_folder_id="folder-1",
        strict_cleanup=False,
        chart_image_sharing_mode="restricted",
    )
    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(create=lambda **kwargs: ("files-create", kwargs)),
        permissions=lambda: SimpleNamespace(
            create=lambda **kwargs: ("perm-create", kwargs)
        ),
    )

    calls: List[Any] = []

    def _exec(request):
        calls.append(request)
        if request[0] == "files-create":
            return {"id": "file-1"}
        return {}

    sleep_calls: List[float] = []
    monkeypatch.setattr(
        google_docs_module, "time", SimpleNamespace(sleep=sleep_calls.append)
    )
    monkeypatch.setattr(
        google_docs_module.Timing,
        "GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S",
        1.5,
    )

    provider._execute_request = _exec

    url, file_id = provider.upload_chart_image("doc-1", b"bytes", "chart.png")
    assert url == "https://drive.google.com/uc?id=file-1"
    assert file_id == "file-1"
    assert [call for call in calls if call[0] == "perm-create"] == []
    assert sleep_calls == []


def test_delete_chart_image_raises_when_strict_cleanup_enabled():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(strict_cleanup=True)
    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(update=lambda **kwargs: ("files-update", kwargs))
    )
    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("forbidden", status=403)
    )

    with pytest.raises(google_docs_module.HttpError):
        provider.delete_chart_image("file-strict")


def test_render_citations_document_end_dedupes_and_appends(monkeypatch):
    provider = _provider_without_init()
    appended: List[Tuple[str, List[Dict[str, Any]]]] = []
    monkeypatch.setattr(
        provider,
        "_render_document_end_citations",
        lambda document_id, citations: appended.append((document_id, citations)),
    )

    provider.render_citations(
        "doc-1",
        {
            "intro": [
                {"source_id": "src-1", "provider": "csv", "display_name": "One"},
            ],
            "details": [
                {"source_id": "src-1", "provider": "csv", "display_name": "One"},
                {"source_id": "src-2", "provider": "csv", "display_name": "Two"},
            ],
        },
        location="document_end",
    )

    assert appended
    document_id, citations = appended[0]
    assert document_id == "doc-1"
    assert [entry["source_id"] for entry in citations] == ["src-1", "src-2"]


def test_render_citations_per_section_routes_to_footnotes(monkeypatch):
    provider = _provider_without_init()
    calls: List[Tuple[str, str, List[Dict[str, Any]]]] = []
    monkeypatch.setattr(
        provider,
        "_render_section_footnote_citations",
        lambda document_id, section_id, citations: calls.append(
            (document_id, section_id, citations)
        ),
    )

    provider.render_citations(
        "doc-2",
        {
            "intro": [
                {"source_id": "src-1", "provider": "csv", "display_name": "One"},
            ],
            "details": [
                {"source_id": "src-2", "provider": "csv", "display_name": "Two"},
            ],
        },
        location="per_section",
    )

    assert calls == [
        (
            "doc-2",
            "intro",
            [{"source_id": "src-1", "provider": "csv", "display_name": "One"}],
        ),
        (
            "doc-2",
            "details",
            [{"source_id": "src-2", "provider": "csv", "display_name": "Two"}],
        ),
    ]


def test_render_document_end_citations_logs_warning_for_invalid_payload(monkeypatch):
    provider = _provider_without_init()
    provider._get_document_content = lambda _document_id: [{"endIndex": 6}]
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs)
        )
    )

    calls: List[Any] = []
    provider._execute_request = lambda request: calls.append(request) or {}

    warnings: List[str] = []
    monkeypatch.setattr(
        google_docs_module.logger,
        "warning",
        lambda message, *args: warnings.append(message % args),
    )

    provider._render_document_end_citations(
        "doc-3",
        [
            {"source_id": "src-invalid", "provider": "csv"},
            {
                "source_id": "src-valid",
                "provider": "csv",
                "display_name": "Valid Source",
            },
        ],
    )

    assert calls
    request = calls[0][1]
    inserted_text = request["body"]["requests"][0]["insertText"]["text"]
    assert "Valid Source" in inserted_text
    assert "src-invalid" not in inserted_text

    assert warnings
    assert "location=document_end" in warnings[0]
    assert "src-invalid" in warnings[0]
