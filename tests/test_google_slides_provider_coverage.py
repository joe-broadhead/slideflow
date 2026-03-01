from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

import slideflow.presentations.providers.google_slides as google_provider_module
from slideflow.presentations.providers.google_slides import (
    GoogleSlidesProvider,
    GoogleSlidesProviderConfig,
)
from slideflow.utilities.exceptions import AuthenticationError


def _provider_without_init() -> GoogleSlidesProvider:
    return object.__new__(google_provider_module.GoogleSlidesProvider)


def _http_error(
    message: str, status: Optional[int] = None, content: Optional[bytes] = None
):
    error = google_provider_module.HttpError(message)
    if status is not None:
        error.resp = SimpleNamespace(status=status)
    if content is not None:
        error.content = content
    return error


def test_google_provider_init_success(monkeypatch):
    captured: Dict[str, Any] = {}

    monkeypatch.setattr(
        google_provider_module,
        "handle_google_credentials",
        lambda _credentials: {"client_email": "svc@example.com"},
    )
    monkeypatch.setattr(
        google_provider_module.Credentials,
        "from_service_account_info",
        lambda info, scopes: captured.update({"info": info, "scopes": scopes})
        or "creds",
    )
    monkeypatch.setattr(
        google_provider_module,
        "build",
        lambda service, version, credentials: f"{service}:{version}:{credentials}",
    )
    monkeypatch.setattr(
        google_provider_module, "_get_rate_limiter", lambda rps: f"rl:{rps}"
    )

    provider = GoogleSlidesProvider(
        GoogleSlidesProviderConfig(
            credentials='{"type":"service_account"}', requests_per_second=2.5
        )
    )

    assert provider.slides_service == "slides:v1:creds"
    assert provider.drive_service == "drive:v3:creds"
    assert provider.rate_limiter == "rl:2.5"
    assert captured["info"] == {"client_email": "svc@example.com"}
    assert captured["scopes"] == google_provider_module.GoogleSlidesProvider.SCOPES


def test_google_provider_init_authentication_failure(monkeypatch):
    monkeypatch.setattr(
        google_provider_module,
        "handle_google_credentials",
        lambda _credentials: {"invalid": True},
    )
    monkeypatch.setattr(
        google_provider_module.Credentials,
        "from_service_account_info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad creds")),
    )

    with pytest.raises(AuthenticationError, match="Credentials authentication failed"):
        GoogleSlidesProvider(GoogleSlidesProviderConfig(credentials='{"invalid":true}'))


def test_google_slides_config_validates_transfer_ownership_target():
    with pytest.raises(ValueError, match="transfer_ownership_to"):
        GoogleSlidesProviderConfig(transfer_ownership_to="not-an-email")

    config = GoogleSlidesProviderConfig(transfer_ownership_to=" owner@example.com ")
    assert config.transfer_ownership_to == "owner@example.com"


@pytest.mark.parametrize(
    ("dimension", "expected"),
    [
        (None, None),
        ({}, None),
        ({"magnitude": "bad", "unit": "PT"}, None),
        ({"magnitude": 12700, "unit": "EMU"}, 1),
        ({"magnitude": 20, "unit": "PT"}, 20),
        ({"magnitude": 20, "unit": "PX"}, None),
    ],
)
def test_dimension_to_points_variants(dimension, expected):
    assert (
        google_provider_module.GoogleSlidesProvider._dimension_to_points(dimension)
        == expected
    )


def test_run_preflight_checks_without_credentials(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(credentials=None, requests_per_second=1.0)
    provider.slides_service = None
    provider.drive_service = None
    provider.rate_limiter = None
    monkeypatch.delenv("GOOGLE_SLIDEFLOW_CREDENTIALS", raising=False)

    checks = provider.run_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}

    assert check_map["google_credentials_present"] is False
    assert check_map["slides_service_initialized"] is False
    assert check_map["drive_service_initialized"] is False
    assert check_map["rate_limiter_initialized"] is False


def test_run_preflight_checks_validates_transfer_target(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(
        credentials=None,
        requests_per_second=1.0,
        transfer_ownership_to="not-an-email",
    )
    provider.slides_service = object()
    provider.drive_service = object()
    provider.rate_limiter = object()
    monkeypatch.delenv("GOOGLE_SLIDEFLOW_CREDENTIALS", raising=False)

    checks = provider.run_preflight_checks()
    check_map = {name: ok for name, ok, _ in checks}

    assert check_map["ownership_transfer_target_valid"] is False


def test_share_presentation_success_and_error(monkeypatch):
    provider = _provider_without_init()
    requests: List[Any] = []
    created_permissions: List[Dict[str, Any]] = []

    class _Permissions:
        def create(self, **kwargs):
            created_permissions.append(kwargs)
            return ("permission-create", kwargs)

    provider.drive_service = SimpleNamespace(permissions=lambda: _Permissions())

    def _exec(request):
        requests.append(request)
        return {}

    provider._execute_request = _exec

    provider.share_presentation(
        "pres-1", ["a@example.com", "b@example.com"], role="reader"
    )

    assert len(requests) == 2
    assert created_permissions[0]["fileId"] == "pres-1"
    assert created_permissions[0]["body"]["emailAddress"] == "a@example.com"

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("share failed")
    )

    with pytest.raises(google_provider_module.HttpError):
        provider.share_presentation("pres-2", ["x@example.com"], role="writer")


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
            return {"id": "pres-1"}
        return {}

    provider._execute_request = _exec
    provider.transfer_presentation_ownership("pres-1", "owner@example.com")

    assert created_permissions == [
        {
            "fileId": "pres-1",
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
        {"id": "pres-2", "driveId": "drive-123"} if request[0] == "files-get" else {}
    )
    with pytest.raises(ValueError, match="Shared Drives"):
        provider.transfer_presentation_ownership("pres-2", "owner@example.com")


def test_get_presentation_page_size_logs_failure_on_exception(monkeypatch):
    provider = _provider_without_init()
    provider.slides_service = SimpleNamespace(
        presentations=lambda: SimpleNamespace(
            get=lambda **_kwargs: ("get-page-size", None)
        )
    )
    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        RuntimeError("api down")
    )

    logs: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []
    monkeypatch.setattr(
        google_provider_module, "log_api_operation", lambda *a, **k: logs.append((a, k))
    )

    assert provider.get_presentation_page_size("pres-1") is None
    assert logs and logs[-1][1]["success"] is False


def test_get_or_create_destination_folder_paths(monkeypatch):
    provider = _provider_without_init()
    google_provider_module._folder_id_cache.clear()

    provider.config = SimpleNamespace(
        presentation_folder_id=None,
        new_folder_name="child",
        new_folder_name_fn=None,
    )
    assert provider._get_or_create_destination_folder() is None

    provider.config = SimpleNamespace(
        presentation_folder_id="parent-1",
        new_folder_name="child",
        new_folder_name_fn=None,
    )
    google_provider_module._folder_id_cache[("parent-1", "child")] = "cached-folder"
    assert provider._get_or_create_destination_folder() == "cached-folder"

    google_provider_module._folder_id_cache.clear()
    files_api = SimpleNamespace(
        list=lambda **kwargs: ("list", kwargs),
        create=lambda **kwargs: ("create", kwargs),
    )
    provider.drive_service = SimpleNamespace(files=lambda: files_api)

    provider._execute_request = lambda request: (
        {"files": [{"id": "existing-folder"}]} if request[0] == "list" else {}
    )
    assert provider._get_or_create_destination_folder() == "existing-folder"

    google_provider_module._folder_id_cache.clear()
    provider._execute_request = lambda request: (
        {"files": []} if request[0] == "list" else {"id": "created-folder"}
    )
    assert provider._get_or_create_destination_folder() == "created-folder"

    google_provider_module._folder_id_cache.clear()
    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("folder lookup failed")
    )
    assert provider._get_or_create_destination_folder() == "parent-1"


def test_create_presentation_success_move_warning_and_failure(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace()

    calls: List[Any] = []
    provider.slides_service = SimpleNamespace(
        presentations=lambda: SimpleNamespace(
            create=lambda **kwargs: ("slides-create", kwargs)
        )
    )
    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(
            get=lambda **kwargs: ("drive-get", kwargs),
            update=lambda **kwargs: ("drive-update", kwargs),
        )
    )

    provider._get_or_create_destination_folder = lambda: None
    provider._execute_request = lambda request: (
        {"presentationId": "pres-1"} if request[0] == "slides-create" else {}
    )
    log_calls: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []
    monkeypatch.setattr(
        google_provider_module,
        "log_api_operation",
        lambda *a, **k: log_calls.append((a, k)),
    )
    assert provider._create_presentation("Deck A") == "pres-1"
    assert log_calls[-1][1]["presentation_id"] == "pres-1"

    provider._get_or_create_destination_folder = lambda: "folder-1"

    def _exec_success(request):
        calls.append(request)
        if request[0] == "slides-create":
            return {"presentationId": "pres-2"}
        if request[0] == "drive-get":
            return {"parents": ["old-parent"]}
        if request[0] == "drive-update":
            return {"id": "pres-2"}
        return {}

    provider._execute_request = _exec_success
    assert provider._create_presentation("Deck B") == "pres-2"
    drive_update_call = [c for c in calls if c[0] == "drive-update"][0][1]
    assert drive_update_call["removeParents"] == "old-parent"

    def _exec_move_fails(request):
        if request[0] == "slides-create":
            return {"presentationId": "pres-3"}
        if request[0] == "drive-get":
            return {"parents": ["old-parent"]}
        if request[0] == "drive-update":
            raise _http_error("move failed")
        return {}

    provider._execute_request = _exec_move_fails
    assert provider._create_presentation("Deck C") == "pres-3"

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("create failed")
    )
    with pytest.raises(google_provider_module.HttpError):
        provider._create_presentation("Deck D")


def test_copy_template_success_and_error():
    provider = _provider_without_init()
    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(copy=lambda **kwargs: ("drive-copy", kwargs))
    )

    provider._get_or_create_destination_folder = lambda: "folder-1"
    provider._execute_request = lambda request: {"id": "copied-1"}
    assert provider._copy_template("template-1", "Deck 1") == "copied-1"

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("copy failed")
    )
    with pytest.raises(google_provider_module.HttpError):
        provider._copy_template("template-2", "Deck 2")


def test_upload_image_to_drive_success_and_error(monkeypatch):
    provider = _provider_without_init()
    provider.config = SimpleNamespace(drive_folder_id=None)
    provider._get_or_create_destination_folder = lambda: "folder-1"

    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(create=lambda **kwargs: ("files-create", kwargs)),
        permissions=lambda: SimpleNamespace(
            create=lambda **kwargs: ("perm-create", kwargs)
        ),
    )

    logs: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []
    monkeypatch.setattr(
        google_provider_module, "log_api_operation", lambda *a, **k: logs.append((a, k))
    )
    monkeypatch.setattr(google_provider_module.time, "sleep", lambda _seconds: None)

    provider._execute_request = lambda request: (
        {"id": "file-123"} if request[0] == "files-create" else {}
    )
    public_url, file_id = provider._upload_image_to_drive(b"png-bytes", "chart.png")
    assert public_url == "https://drive.google.com/uc?id=file-123"
    assert file_id == "file-123"
    assert logs[-1][0][2] is True

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("upload failed")
    )
    with pytest.raises(google_provider_module.HttpError):
        provider._upload_image_to_drive(b"png-bytes", "chart.png")


def test_batch_update_error_logs_and_raises(monkeypatch):
    provider = _provider_without_init()
    provider.slides_service = SimpleNamespace(
        presentations=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs)
        )
    )
    logs: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []
    monkeypatch.setattr(
        google_provider_module, "log_api_operation", lambda *a, **k: logs.append((a, k))
    )

    error = _http_error("batch failed", content=b'{"error":"invalid"}')
    provider._execute_request = lambda _request: (_ for _ in ()).throw(error)

    with pytest.raises(google_provider_module.HttpError):
        provider._batch_update("pres-1", [{"replaceAllText": {}}])

    assert logs and logs[-1][0][2] is False
    assert logs[-1][1]["error"] == '{"error":"invalid"}'


def test_delete_chart_image_handles_permission_and_other_errors():
    provider = _provider_without_init()
    provider.drive_service = SimpleNamespace(
        files=lambda: SimpleNamespace(update=lambda **kwargs: ("files-update", kwargs))
    )

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("forbidden", status=403)
    )
    provider.delete_chart_image("file-1")

    provider._execute_request = lambda _request: (_ for _ in ()).throw(
        _http_error("server", status=500)
    )
    provider.delete_chart_image("file-2")


def test_render_citations_inserts_sources_into_speaker_notes():
    provider = _provider_without_init()
    provider._get_speaker_notes_targets = lambda _presentation_id: {
        "slide-1": ("notes-1", 4)
    }
    captured_requests: List[Dict[str, Any]] = []
    provider._batch_update = (
        lambda _presentation_id, requests: captured_requests.extend(requests) or {}
    )

    provider.render_citations(
        "pres-1",
        {
            "slide-1": [
                {
                    "source_id": "source-1",
                    "provider": "csv",
                    "display_name": "CSV Source",
                    "file_url": "https://example.com/source.csv",
                }
            ]
        },
        location="per_slide",
    )

    assert len(captured_requests) == 1
    insert_request = captured_requests[0]["insertText"]
    assert insert_request["objectId"] == "notes-1"
    assert insert_request["insertionIndex"] == 4
    assert "Sources" in insert_request["text"]
    assert "CSV Source" in insert_request["text"]


def test_render_citations_document_end_uses_first_slide_notes():
    provider = _provider_without_init()
    provider._get_speaker_notes_targets = lambda _presentation_id: {
        "slide-a": ("notes-a", 1),
        "slide-b": ("notes-b", 2),
    }
    captured_requests: List[Dict[str, Any]] = []
    provider._batch_update = (
        lambda _presentation_id, requests: captured_requests.extend(requests) or {}
    )

    provider.render_citations(
        "pres-1",
        {
            "slide-a": [
                {"source_id": "src-1", "provider": "csv", "display_name": "One"}
            ],
            "slide-b": [
                {"source_id": "src-2", "provider": "csv", "display_name": "Two"}
            ],
        },
        location="document_end",
    )

    assert len(captured_requests) == 1
    insert_request = captured_requests[0]["insertText"]
    assert insert_request["objectId"] == "notes-a"
    assert "One" in insert_request["text"]
    assert "Two" in insert_request["text"]
