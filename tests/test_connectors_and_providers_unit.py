import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import ClassVar, Literal

import pandas as pd
import pytest

import slideflow.data.connectors.base as base_connectors_module
import slideflow.data.connectors.databricks as databricks_module
import slideflow.presentations.providers.factory as provider_factory_module
import slideflow.presentations.providers.google_slides as google_provider_module
import slideflow.presentations.rate_limiter as presentation_rate_limiter_module
from slideflow.constants import Defaults
from slideflow.presentations.config import ProviderConfig
from slideflow.presentations.providers.base import (
    PresentationProvider,
    PresentationProviderConfig,
    ProviderPresentationResult,
    ProviderSlideResult,
)
from slideflow.utilities.exceptions import ConfigurationError, DataSourceError


class DummyConnector(base_connectors_module.DataConnector):
    def __init__(self, token: str):
        self.token = token
        self.connected = False
        self.disconnected = False

    def connect(self):
        self.connected = True
        return "connected"

    def disconnect(self) -> None:
        self.disconnected = True

    def fetch_data(self) -> pd.DataFrame:
        return pd.DataFrame({"token": [self.token]})


class DummySourceConfig(base_connectors_module.BaseSourceConfig):
    type: Literal["dummy"] = "dummy"
    token: str
    connector_class: ClassVar = DummyConnector


class CountingConnector(base_connectors_module.DataConnector):
    _fetch_calls = 0
    _fetch_lock = threading.Lock()

    def __init__(self, token: str):
        self.token = token

    @classmethod
    def reset_calls(cls):
        with cls._fetch_lock:
            cls._fetch_calls = 0

    @classmethod
    def fetch_calls(cls) -> int:
        with cls._fetch_lock:
            return cls._fetch_calls

    def fetch_data(self) -> pd.DataFrame:
        with self._fetch_lock:
            type(self)._fetch_calls += 1
        time.sleep(0.05)
        return pd.DataFrame({"token": [self.token]})


class CountingSourceConfig(base_connectors_module.BaseSourceConfig):
    type: Literal["counting"] = "counting"
    token: str
    connector_class: ClassVar = CountingConnector


class DummyProviderConfig(PresentationProviderConfig):
    provider_type: Literal["dummy_provider"] = "dummy_provider"
    token: str


class DummyProvider(PresentationProvider):
    def create_presentation(self, name: str, template_id=None) -> str:
        return f"{name}:{template_id or 'none'}"

    def upload_chart_image(
        self, presentation_id: str, image_data: bytes, filename: str
    ):
        return ("https://example/image.png", "file-id")

    def insert_chart_to_slide(
        self,
        presentation_id: str,
        slide_id: str,
        image_url: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        return None

    def replace_text_in_slide(
        self, presentation_id: str, slide_id: str, placeholder: str, replacement: str
    ) -> int:
        return 1

    def share_presentation(self, presentation_id: str, emails, role="writer") -> None:
        return None

    def get_presentation_url(self, presentation_id: str) -> str:
        return f"https://example/{presentation_id}"

    def delete_chart_image(self, file_id: str) -> None:
        return None


def test_data_connector_context_manager_and_base_source_cache(monkeypatch):
    connector = DummyConnector("abc")
    with connector as active:
        assert active is connector
        assert connector.connected is True
    assert connector.disconnected is True

    class FakeCache:
        def __init__(self):
            self.store = {}
            self.set_calls = 0

        def _key(self, source_type, kwargs):
            return (source_type, tuple(sorted(kwargs.items())))

        def get(self, source_type, **kwargs):
            return self.store.get(self._key(source_type, kwargs))

        def set(self, data, source_type, **kwargs):
            self.set_calls += 1
            self.store[self._key(source_type, kwargs)] = data

        def get_or_load(self, source_type, loader, **kwargs):
            cached = self.get(source_type, **kwargs)
            if cached is not None:
                return cached
            data = loader()
            self.set(data, source_type, **kwargs)
            return data

    fake_cache = FakeCache()
    monkeypatch.setattr(base_connectors_module, "get_data_cache", lambda: fake_cache)

    config = DummySourceConfig(name="demo", type="dummy", token="secret")
    first = config.fetch_data()
    second = config.fetch_data()

    assert first.to_dict(orient="records")[0]["token"] == "secret"
    assert second is first
    assert fake_cache.set_calls == 1


def test_base_source_config_fetch_data_deduplicates_concurrent_connector_fetches():
    cache = base_connectors_module.get_data_cache()
    cache.enable()
    cache.clear()
    CountingConnector.reset_calls()

    config = CountingSourceConfig(name="shared", type="counting", token="secret")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _i: config.fetch_data(), range(8)))

    assert CountingConnector.fetch_calls() == 1
    assert all(result is results[0] for result in results)

    cache.clear()


def test_databricks_connector_connect_disconnect_and_fetch(monkeypatch):
    connect_calls = []

    class FakeArrow:
        def to_pandas(self):
            return pd.DataFrame({"value": [1, 2]})

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query):
            self.query = query

        def fetchall_arrow(self):
            return FakeArrow()

    class FakeConnection:
        def __init__(self):
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def close(self):
            self.closed = True

    fake_conn = FakeConnection()

    def fake_connect(**kwargs):
        connect_calls.append(kwargs)
        return fake_conn

    monkeypatch.setattr(databricks_module.sql, "connect", fake_connect)
    monkeypatch.setenv("DATABRICKS_HOST", "host")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "http-path")
    monkeypatch.setenv("DATABRICKS_ACCESS_TOKEN", "token")

    api_logs = []
    data_logs = []
    monkeypatch.setattr(
        databricks_module, "log_api_operation", lambda *a, **k: api_logs.append((a, k))
    )
    monkeypatch.setattr(
        databricks_module,
        "log_data_operation",
        lambda *a, **k: data_logs.append((a, k)),
    )

    connector = databricks_module.DatabricksConnector("SELECT 1")
    assert connector.connect() is fake_conn
    assert connector.connect() is fake_conn  # cached connection reuse
    assert len(connect_calls) == 1
    assert connect_calls[0]["_socket_timeout"] == Defaults.DATABRICKS_SOCKET_TIMEOUT_S
    assert (
        connect_calls[0]["_retry_stop_after_attempts_count"]
        == Defaults.DATABRICKS_RETRY_MAX_ATTEMPTS
    )
    assert (
        connect_calls[0]["_retry_stop_after_attempts_duration"]
        == Defaults.DATABRICKS_RETRY_MAX_DURATION_S
    )
    assert connect_calls[0]["_retry_delay_min"] == Defaults.DATABRICKS_RETRY_DELAY_MIN_S
    assert connect_calls[0]["_retry_delay_max"] == Defaults.DATABRICKS_RETRY_DELAY_MAX_S

    result = connector.fetch_data()
    assert len(result) == 2
    assert api_logs and api_logs[-1][0][2] is True
    assert data_logs

    connector.disconnect()
    assert fake_conn.closed is True
    assert connector._connection is None


def test_databricks_connector_connect_fails_fast_with_missing_env(monkeypatch):
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_HTTP_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_ACCESS_TOKEN", raising=False)

    connector = databricks_module.DatabricksConnector("SELECT 1")

    with pytest.raises(DataSourceError, match="Missing required environment variable"):
        connector.connect()


def test_databricks_connector_requires_optional_dependency(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "host")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "http-path")
    monkeypatch.setenv("DATABRICKS_ACCESS_TOKEN", "token")
    monkeypatch.setattr(databricks_module, "sql", None)

    connector = databricks_module.DatabricksConnector("SELECT 1")
    with pytest.raises(
        DataSourceError,
        match=r"slideflow-presentations\[databricks\]",
    ):
        connector.connect()


def test_databricks_connector_applies_explicit_retry_and_timeout_overrides(monkeypatch):
    connect_calls = []

    class FakeConnection:
        def close(self):
            return None

    def fake_connect(**kwargs):
        connect_calls.append(kwargs)
        return FakeConnection()

    monkeypatch.setattr(databricks_module.sql, "connect", fake_connect)
    monkeypatch.setenv("DATABRICKS_HOST", "host")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "http-path")
    monkeypatch.setenv("DATABRICKS_ACCESS_TOKEN", "token")

    connector = databricks_module.DatabricksConnector(
        "SELECT 1",
        socket_timeout_s=30.0,
        retry_max_attempts=5,
        retry_max_duration_s=120.0,
        retry_delay_min_s=0.5,
        retry_delay_max_s=5.0,
    )
    connector.connect()

    assert connect_calls[0]["_socket_timeout"] == 30.0
    assert connect_calls[0]["_retry_stop_after_attempts_count"] == 5
    assert connect_calls[0]["_retry_stop_after_attempts_duration"] == 120.0
    assert connect_calls[0]["_retry_delay_min"] == 0.5
    assert connect_calls[0]["_retry_delay_max"] == 5.0


def test_databricks_connector_connect_classifies_auth_errors(monkeypatch):
    def fake_connect(**_kwargs):
        raise RuntimeError("invalid access token")

    monkeypatch.setattr(databricks_module.sql, "connect", fake_connect)
    monkeypatch.setenv("DATABRICKS_HOST", "host")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "http-path")
    monkeypatch.setenv("DATABRICKS_ACCESS_TOKEN", "token")

    connector = databricks_module.DatabricksConnector("SELECT 1")
    with pytest.raises(DataSourceError, match=r"databricks\[authentication\]"):
        connector.connect()


def test_databricks_connector_fetch_logs_failure(monkeypatch):
    class FailingCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query):
            raise RuntimeError("boom")

    class FailingConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FailingCursor()

    logs = []
    monkeypatch.setattr(
        databricks_module, "log_api_operation", lambda *a, **k: logs.append((a, k))
    )

    connector = databricks_module.DatabricksConnector("SELECT fail")
    monkeypatch.setattr(connector, "connect", lambda: FailingConnection())

    with pytest.raises(DataSourceError, match=r"databricks\[query\]"):
        connector.fetch_data()

    assert logs and logs[-1][0][2] is False


def test_databricks_connector_fetch_classifies_auth_errors(monkeypatch):
    class AuthFailingCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query):
            raise RuntimeError("invalid access token")

    class AuthFailingConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return AuthFailingCursor()

    connector = databricks_module.DatabricksConnector("SELECT fail")
    monkeypatch.setattr(connector, "connect", lambda: AuthFailingConnection())

    with pytest.raises(DataSourceError, match=r"databricks\[authentication\]"):
        connector.fetch_data()


def test_databricks_sql_executor_delegates_to_databricks_connector(monkeypatch):
    captured = {}

    class _ConnectorStub:
        def __init__(self, query):
            captured["query"] = query

        def fetch_data(self):
            return pd.DataFrame({"value": [42]})

    monkeypatch.setattr(databricks_module, "DatabricksConnector", _ConnectorStub)

    executor = databricks_module.DatabricksSQLExecutor()
    result = executor.execute("SELECT 42")

    assert captured["query"] == "SELECT 42"
    assert result.to_dict(orient="records") == [{"value": 42}]


def test_provider_result_models_and_factory_registration():
    result = ProviderPresentationResult(
        presentation_id="p1",
        presentation_url="https://example/p1",
        slide_results=[
            ProviderSlideResult(
                slide_id="s1", chart_urls=[("u1", "p1")], replacements_made=2
            ),
            ProviderSlideResult(
                slide_id="s2",
                chart_urls=[("u2", "p2"), ("u3", "p3")],
                replacements_made=1,
            ),
        ],
    )
    assert result.total_charts_generated == 3
    assert result.total_replacements_made == 3

    provider_factory_module.ProviderFactory.register_provider(
        "dummy_provider",
        DummyProvider,
        DummyProviderConfig,
    )
    config = ProviderConfig(type="dummy_provider", config={"token": "abc"})
    provider = provider_factory_module.ProviderFactory.create_provider(config)

    assert isinstance(provider, DummyProvider)
    assert provider.config.token == "abc"
    assert (
        "dummy_provider"
        in provider_factory_module.ProviderFactory.get_available_providers()
    )
    assert (
        provider_factory_module.ProviderFactory.get_provider_class("dummy_provider")
        is DummyProvider
    )
    assert (
        provider_factory_module.ProviderFactory.get_config_class("dummy_provider")
        is DummyProviderConfig
    )


def test_provider_factory_rejects_unsupported_provider():
    with pytest.raises(ConfigurationError, match="Unsupported provider type"):
        provider_factory_module.ProviderFactory.create_provider(
            ProviderConfig(type="missing_provider", config={})
        )


def test_google_provider_helper_methods(monkeypatch):
    provider = object.__new__(google_provider_module.GoogleSlidesProvider)
    provider.config = SimpleNamespace(template_id="template-1")

    copy_calls = []
    create_calls = []
    monkeypatch.setattr(
        provider, "_copy_template", lambda t, n: copy_calls.append((t, n)) or "copied"
    )
    monkeypatch.setattr(
        provider, "_create_presentation", lambda n: create_calls.append(n) or "created"
    )
    monkeypatch.setattr(
        provider, "_upload_image_to_drive", lambda data, name: ("https://img", "file-1")
    )

    assert provider.create_presentation("Deck") == "copied"
    assert copy_calls == [("template-1", "Deck")]

    assert provider.create_presentation("Deck2", template_id="template-2") == "copied"
    assert copy_calls[-1] == ("template-2", "Deck2")

    provider.config = SimpleNamespace(template_id=None)
    assert provider.create_presentation("Plain Deck") == "created"
    assert create_calls == ["Plain Deck"]

    assert provider.upload_chart_image("p1", b"bytes", "x.png") == (
        "https://img",
        "file-1",
    )

    batch_calls = []
    monkeypatch.setattr(
        provider,
        "_batch_update",
        lambda pres_id, reqs: batch_calls.append((pres_id, reqs)) or {},
    )
    provider.insert_chart_to_slide("p1", "s1", "https://img", 1, 2, 3, 4)
    assert batch_calls and batch_calls[0][0] == "p1"
    assert batch_calls[0][1][0]["createImage"]["url"] == "https://img"

    monkeypatch.setattr(
        provider,
        "_batch_update",
        lambda _pres_id, _reqs: {
            "replies": [{"replaceAllText": {"occurrencesChanged": 7}}]
        },
    )
    assert provider.replace_text_in_slide("p1", "s1", "{{X}}", "Y") == 7

    monkeypatch.setattr(provider, "_batch_update", lambda _pres_id, _reqs: {})
    assert provider.replace_text_in_slide("p1", "s1", "{{X}}", "Y") == 0
    assert provider.get_presentation_url("abc123").endswith("/abc123")


def test_google_provider_execute_request_and_batch_update(monkeypatch):
    provider = object.__new__(google_provider_module.GoogleSlidesProvider)
    wait_calls = []
    provider.rate_limiter = SimpleNamespace(wait=lambda: wait_calls.append(True))

    class FakeRequest:
        def execute(self, num_retries):
            return {"num_retries": num_retries}

    assert provider._execute_request(FakeRequest()) == {"num_retries": 3}
    assert wait_calls == [True]

    assert provider._batch_update("p1", []) == {}

    presentations = SimpleNamespace(
        batchUpdate=lambda presentationId, body: ("request", presentationId, body)
    )
    provider.slides_service = SimpleNamespace(presentations=lambda: presentations)
    monkeypatch.setattr(
        provider, "_execute_request", lambda request: {"request": request}
    )
    logs = []
    monkeypatch.setattr(
        google_provider_module, "log_api_operation", lambda *a, **k: logs.append((a, k))
    )

    response = provider._batch_update("p1", [{"replaceAllText": {}}])
    assert response["request"][1] == "p1"
    assert logs and logs[-1][0][2] is True


def test_google_provider_upload_image_uses_configured_propagation_delay(monkeypatch):
    provider = object.__new__(google_provider_module.GoogleSlidesProvider)
    provider.config = SimpleNamespace(drive_folder_id="folder-1")

    class _Files:
        def create(self, **kwargs):
            return ("file-create", kwargs)

    class _Permissions:
        def create(self, **kwargs):
            return ("permission-create", kwargs)

    provider.drive_service = SimpleNamespace(
        files=lambda: _Files(),
        permissions=lambda: _Permissions(),
    )

    executed = []

    def _execute(request):
        executed.append(request)
        if len(executed) == 1:
            return {"id": "file-1"}
        return {}

    monkeypatch.setattr(provider, "_execute_request", _execute)
    monkeypatch.setattr(
        google_provider_module,
        "log_api_operation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        google_provider_module.Timing,
        "GOOGLE_DRIVE_PERMISSION_PROPAGATION_DELAY_S",
        0.25,
    )
    sleep_calls = []
    monkeypatch.setattr(
        google_provider_module.time, "sleep", lambda delay: sleep_calls.append(delay)
    )

    public_url, file_id = provider._upload_image_to_drive(b"image-bytes", "chart.png")

    assert file_id == "file-1"
    assert public_url == "https://drive.google.com/uc?id=file-1"
    assert sleep_calls == [0.25]
    assert len(executed) == 2


def test_google_rate_limiter_singleton_update():
    presentation_rate_limiter_module.reset_google_api_rate_limiter()
    rl1 = google_provider_module._get_rate_limiter(1.0)
    rl2 = google_provider_module._get_rate_limiter(5.0)
    rl3 = google_provider_module._get_rate_limiter(5.0, force_update=True)

    assert rl1 is rl2 is rl3
    assert rl3.rate == 5.0


def test_google_provider_page_size_and_preflight(monkeypatch):
    provider = object.__new__(google_provider_module.GoogleSlidesProvider)
    provider.config = SimpleNamespace(credentials=None, requests_per_second=3.0)
    provider.slides_service = SimpleNamespace(
        presentations=lambda: SimpleNamespace(
            get=lambda **_kwargs: "request",
        )
    )
    provider.drive_service = object()
    provider.rate_limiter = object()

    monkeypatch.setattr(
        provider,
        "_execute_request",
        lambda _request: {
            "pageSize": {
                "width": {"magnitude": 9144000, "unit": "EMU"},
                "height": {"magnitude": 6858000, "unit": "EMU"},
            }
        },
    )
    monkeypatch.setenv("GOOGLE_SLIDEFLOW_CREDENTIALS", '{"type":"service_account"}')

    assert provider.get_presentation_page_size("p1") == (720, 540)

    checks = provider.run_preflight_checks()
    assert checks
    assert all(ok for _name, ok, _detail in checks)


def test_google_provider_page_size_returns_none_on_invalid_shape(monkeypatch):
    provider = object.__new__(google_provider_module.GoogleSlidesProvider)
    provider.slides_service = SimpleNamespace(
        presentations=lambda: SimpleNamespace(get=lambda **_kwargs: "request")
    )
    provider.rate_limiter = SimpleNamespace(wait=lambda: None)

    monkeypatch.setattr(provider, "_execute_request", lambda _request: {"pageSize": {}})

    assert provider.get_presentation_page_size("p1") is None
