from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

import slideflow.presentations.providers.factory as provider_factory_module
import slideflow.presentations.providers.google_docs as google_docs_module
from slideflow.constants import Environment
from slideflow.presentations.config import ProviderConfig
from slideflow.presentations.providers.google_docs import (
    GoogleDocsProvider,
    GoogleDocsProviderConfig,
)
from slideflow.utilities.exceptions import AuthenticationError


def _provider_without_init() -> GoogleDocsProvider:
    return object.__new__(google_docs_module.GoogleDocsProvider)


def _http_error(
    message: str, status: Optional[int] = None, content: Optional[bytes] = None
):
    error = google_docs_module.HttpError(message)
    if status is not None:
        error.resp = SimpleNamespace(status=status)
    if content is not None:
        error.content = content
    return error


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
    monkeypatch.setattr(
        google_docs_module,
        "build",
        lambda service, version, credentials: f"{service}:{version}:{credentials}",
    )
    monkeypatch.setattr(
        google_docs_module, "_get_rate_limiter", lambda rps: f"rl:{rps}"
    )

    provider = GoogleDocsProvider(
        GoogleDocsProviderConfig(
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
        GoogleDocsProvider(GoogleDocsProviderConfig(credentials='{"invalid":true}'))


def test_google_docs_provider_factory_registration():
    config = ProviderConfig(
        type="google_docs",
        config={"credentials": '{"type":"service_account"}'},
    )
    provider = provider_factory_module.ProviderFactory.create_provider(config)

    assert isinstance(provider, GoogleDocsProvider)
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


def test_insert_chart_and_replace_text_requests():
    provider = _provider_without_init()
    provider.docs_service = SimpleNamespace(
        documents=lambda: SimpleNamespace(
            batchUpdate=lambda **kwargs: ("batch-update", kwargs)
        )
    )

    requests: List[Any] = []
    provider._execute_request = lambda request: requests.append(request) or {
        "replies": [{"replaceAllText": {"occurrencesChanged": 4}}]
    }

    provider.insert_chart_to_slide(
        "doc-1", "section-1", "https://img.example/chart.png", 10, 20, 300, 200
    )
    assert requests[0][0] == "batch-update"
    insert_payload = requests[0][1]["body"]["requests"][0]["insertInlineImage"]
    assert insert_payload["uri"] == "https://img.example/chart.png"

    replaced = provider.replace_text_in_slide(
        "doc-1", "section-1", "{{PLACEHOLDER}}", "VALUE"
    )
    assert replaced == 4
    replace_payload = requests[1][1]["body"]["requests"][0]["replaceAllText"]
    assert replace_payload["containsText"]["text"] == "{{PLACEHOLDER}}"


def test_upload_share_and_delete_paths():
    provider = _provider_without_init()
    provider.config = SimpleNamespace(drive_folder_id="folder-1", strict_cleanup=False)

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
    provider.config = SimpleNamespace(drive_folder_id="folder-1", strict_cleanup=False)
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
