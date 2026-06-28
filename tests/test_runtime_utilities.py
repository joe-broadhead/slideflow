import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import pytest

import slideflow.data.cache as data_cache_module
import slideflow.presentations.rate_limiter as presentation_rate_limiter_module
import slideflow.utilities.rate_limiter as rate_limiter_module
from slideflow.constants import Environment
from slideflow.utilities.auth import (
    describe_google_credentials_source,
    handle_google_credentials,
    load_google_credentials,
)
from slideflow.utilities.exceptions import AuthenticationError


def _records(df):
    return df.to_dict(orient="records")


def _first_value(df, column="value"):
    return _records(df)[0][column]


def _assert_frame_records_equal(left, right):
    assert _records(left) == _records(right)


def test_data_source_cache_lifecycle_and_singleton_behavior():
    cache = data_cache_module.get_data_cache()
    cache.enable()
    cache.clear()

    df = pd.DataFrame({"value": [1]})
    cache.set(df, source_type="csv", file_path="data.csv")

    cached = cache.get("csv", file_path="data.csv")
    assert cached is not None
    _assert_frame_records_equal(cached, df)
    assert cached is not df
    assert cache.size == 1
    assert cache.is_enabled is True
    assert data_cache_module.get_data_cache() is cache

    df["value"] = [2]
    cached["value"] = [3]
    fresh_cached = cache.get("csv", file_path="data.csv")
    assert fresh_cached is not None
    assert _first_value(fresh_cached) == 1

    info = cache.get_cache_info()
    assert info["enabled"] is True
    assert info["size"] == 1
    assert info["max_entries"] == cache.max_entries
    assert info["cached_sources"]

    cache.disable()
    assert cache.is_enabled is False
    assert cache.size == 0
    assert cache.get("csv", file_path="data.csv") is None

    cache.enable()
    assert cache.is_enabled is True
    cache.clear()


def test_data_source_cache_key_generation_is_order_stable():
    cache = data_cache_module.DataSourceCache()
    key_a = cache._generate_key("databricks", query="select 1", target="prod")
    key_b = cache._generate_key("databricks", target="prod", query="select 1")
    assert key_a == key_b


def test_data_source_cache_key_generation_is_order_stable_for_nested_values():
    cache = data_cache_module.DataSourceCache()
    key_a = cache._generate_key(
        "dbt",
        query="select 1",
        vars={
            "country": "US",
            "filters": {"regions": ["NA", "EU"], "active": True},
            "flags": {"b", "a"},
        },
    )
    key_b = cache._generate_key(
        "dbt",
        vars={
            "flags": {"a", "b"},
            "filters": {"active": True, "regions": ["NA", "EU"]},
            "country": "US",
        },
        query="select 1",
    )
    assert key_a == key_b


def test_data_source_cache_key_generation_distinguishes_dict_key_types():
    cache = data_cache_module.DataSourceCache()
    key_with_int = cache._generate_key(
        "dbt",
        vars={
            "filters": {
                "country": "US",
                1: "int-key",
            }
        },
    )
    key_with_string = cache._generate_key(
        "dbt",
        vars={
            "filters": {
                "country": "US",
                "1": "string-key",
            }
        },
    )
    assert key_with_int != key_with_string


def test_data_source_cache_key_generation_distinguishes_tuple_from_list():
    cache = data_cache_module.DataSourceCache()
    key_with_tuple = cache._generate_key(
        "dbt",
        vars={"dimensions": ("region", "segment")},
    )
    key_with_list = cache._generate_key(
        "dbt",
        vars={"dimensions": ["region", "segment"]},
    )
    assert key_with_tuple != key_with_list


def test_data_source_cache_logs_model_dump_normalization_failures(monkeypatch):
    cache = data_cache_module.DataSourceCache()
    debug_calls = []
    monkeypatch.setattr(
        data_cache_module.logger,
        "debug",
        lambda *args, **kwargs: debug_calls.append((args, kwargs)),
    )

    class BrokenDump:
        def model_dump(self):
            raise RuntimeError("boom")

        def __repr__(self):
            return "<BrokenDump>"

    key = cache._generate_key("dbt", vars={"broken": BrokenDump()})

    assert key
    assert debug_calls
    first_args = debug_calls[0][0]
    assert "model_dump failed" in first_args[0]


def test_data_source_cache_enforces_lru_entry_cap(monkeypatch):
    monkeypatch.setenv(Environment.SLIDEFLOW_DATA_CACHE_MAX_ENTRIES, "2")
    cache = data_cache_module.get_data_cache()
    cache.enable()
    cache.clear()
    original_max_entries = cache.max_entries
    cache._max_entries = 2

    try:
        df_a = pd.DataFrame({"value": [1]})
        df_b = pd.DataFrame({"value": [2]})
        df_c = pd.DataFrame({"value": [3]})

        cache.set(df_a, source_type="csv", file_path="a.csv")
        cache.set(df_b, source_type="csv", file_path="b.csv")
        assert cache.size == 2

        # Touch a.csv so b.csv becomes least-recently-used.
        cached_a = cache.get("csv", file_path="a.csv")
        assert cached_a is not None
        _assert_frame_records_equal(cached_a, df_a)
        assert cached_a is not df_a

        cache.set(df_c, source_type="csv", file_path="c.csv")
        assert cache.size == 2
        cached_a = cache.get("csv", file_path="a.csv")
        assert cached_a is not None
        _assert_frame_records_equal(cached_a, df_a)
        assert cache.get("csv", file_path="b.csv") is None
        cached_c = cache.get("csv", file_path="c.csv")
        assert cached_c is not None
        _assert_frame_records_equal(cached_c, df_c)
        assert cached_c is not df_c
    finally:
        cache._max_entries = original_max_entries
        cache.clear()


def test_data_source_cache_singleton_init_is_thread_safe():
    data_cache_module.DataSourceCache._instance = None

    def create_cache_instance_id() -> int:
        return id(data_cache_module.DataSourceCache())

    with ThreadPoolExecutor(max_workers=16) as executor:
        instance_ids = list(
            executor.map(lambda _i: create_cache_instance_id(), range(64))
        )

    assert len(set(instance_ids)) == 1


def test_data_source_cache_invalid_env_max_entries_falls_back(monkeypatch):
    monkeypatch.setenv(Environment.SLIDEFLOW_DATA_CACHE_MAX_ENTRIES, "not-an-int")
    cache = data_cache_module.get_data_cache()
    cache.enable()
    assert cache.max_entries > 0


def test_data_source_cache_get_or_load_deduplicates_concurrent_loads():
    cache = data_cache_module.get_data_cache()
    cache.enable()
    cache.clear()

    load_calls = 0
    counter_lock = threading.Lock()
    start_barrier = threading.Barrier(8)
    expected_df = pd.DataFrame({"value": [42]})

    def loader():
        nonlocal load_calls
        with counter_lock:
            load_calls += 1
        time.sleep(0.05)
        return expected_df

    def worker():
        start_barrier.wait()
        return cache.get_or_load("csv", loader, file_path="shared.csv")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _i: worker(), range(8)))

    assert load_calls == 1
    assert len({id(result) for result in results}) == len(results)
    for result in results:
        _assert_frame_records_equal(result, expected_df)

    for result in results:
        result["value"] = [-1]
    cached = cache.get("csv", file_path="shared.csv")
    assert cached is not None
    assert _first_value(cached) == 42

    cache.clear()


def test_data_source_cache_get_or_load_unblocks_waiters_on_base_exception():
    cache = data_cache_module.get_data_cache()
    cache.enable()
    cache.clear()

    load_calls = 0
    counter_lock = threading.Lock()
    start_barrier = threading.Barrier(2)
    expected_df = pd.DataFrame({"value": [99]})

    class LoaderExit(BaseException):
        pass

    def loader():
        nonlocal load_calls
        with counter_lock:
            load_calls += 1
            current = load_calls
        time.sleep(0.05)
        if current == 1:
            raise LoaderExit("exit")
        return expected_df

    def worker():
        start_barrier.wait()
        return cache.get_or_load("csv", loader, file_path="shared-base-exception.csv")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        completed = list(as_completed(futures, timeout=2))

    assert len(completed) == 2

    outcomes = []
    for future in completed:
        try:
            outcomes.append(future.result())
        except LoaderExit as error:
            outcomes.append(error)

    assert any(isinstance(item, LoaderExit) for item in outcomes)
    data_results = [item for item in outcomes if isinstance(item, pd.DataFrame)]
    assert len(data_results) == 1
    _assert_frame_records_equal(data_results[0], expected_df)
    assert load_calls == 2

    cache.clear()


def test_data_source_cache_disable_unblocks_waiters(monkeypatch):
    cache = data_cache_module.get_data_cache()
    cache.enable()
    cache.clear()

    real_event = threading.Event
    loader_started = real_event()
    release_loader = real_event()
    waiter_waiting = real_event()
    counter_lock = threading.Lock()
    load_calls = 0

    class TrackingEvent:
        def __init__(self):
            self._event = real_event()

        def set(self):
            self._event.set()

        def wait(self, timeout=None):
            waiter_waiting.set()
            return self._event.wait(timeout)

    monkeypatch.setattr(cache, "_new_inflight_event", lambda: TrackingEvent())

    def loader():
        nonlocal load_calls
        with counter_lock:
            load_calls += 1
            current = load_calls
        if current == 1:
            loader_started.set()
            assert release_loader.wait(2), "owner loader was not released"
        return pd.DataFrame({"value": [current]})

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(cache.get_or_load, "csv", loader, file_path="slow.csv")
        assert loader_started.wait(2), "owner loader did not start"

        waiter = executor.submit(cache.get_or_load, "csv", loader, file_path="slow.csv")
        assert waiter_waiting.wait(2), "waiter did not block on in-flight load"

        cache.disable()

        waiter_result = waiter.result(timeout=2)
        assert _first_value(waiter_result) == 2
        assert owner.done() is False

        release_loader.set()
        owner_result = owner.result(timeout=2)
        assert _first_value(owner_result) == 1

    assert load_calls == 2
    assert cache.size == 0
    cache.enable()
    cache.clear()


def test_data_source_cache_clear_unblocks_waiters_and_prevents_stale_fill(
    monkeypatch,
):
    cache = data_cache_module.get_data_cache()
    cache.enable()
    cache.clear()

    real_event = threading.Event
    loader_started = real_event()
    release_loader = real_event()
    waiter_waiting = real_event()
    counter_lock = threading.Lock()
    load_calls = 0

    class TrackingEvent:
        def __init__(self):
            self._event = real_event()

        def set(self):
            self._event.set()

        def wait(self, timeout=None):
            waiter_waiting.set()
            return self._event.wait(timeout)

    monkeypatch.setattr(cache, "_new_inflight_event", lambda: TrackingEvent())

    def loader():
        nonlocal load_calls
        with counter_lock:
            load_calls += 1
            current = load_calls
        if current == 1:
            loader_started.set()
            assert release_loader.wait(2), "owner loader was not released"
        return pd.DataFrame({"value": [current]})

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(cache.get_or_load, "csv", loader, file_path="slow.csv")
        assert loader_started.wait(2), "owner loader did not start"

        waiter = executor.submit(cache.get_or_load, "csv", loader, file_path="slow.csv")
        assert waiter_waiting.wait(2), "waiter did not block on in-flight load"

        cache.clear()

        waiter_result = waiter.result(timeout=2)
        assert _first_value(waiter_result) == 2

        release_loader.set()
        owner_result = owner.result(timeout=2)
        assert _first_value(owner_result) == 1

    cached = cache.get("csv", file_path="slow.csv")
    assert cached is not None
    assert _first_value(cached) == 2
    assert load_calls == 2

    cache.clear()


def test_handle_google_credentials_from_file_and_env(tmp_path, monkeypatch):
    payload = {"client_email": "svc@example.com", "private_key": "abc"}
    creds_path = tmp_path / "creds.json"
    creds_path.write_text(json.dumps(payload))

    assert handle_google_credentials(str(creds_path)) == payload

    monkeypatch.setenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, json.dumps(payload))
    assert handle_google_credentials("null") == payload
    assert handle_google_credentials(None) == payload


def test_handle_google_credentials_custom_env_precedence(monkeypatch):
    payload_docs = {"client_email": "docs@example.com", "private_key": "abc"}
    payload_slides = {"client_email": "slides@example.com", "private_key": "def"}
    monkeypatch.setenv(Environment.GOOGLE_DOCS_CREDENTIALS, json.dumps(payload_docs))
    monkeypatch.setenv(
        Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, json.dumps(payload_slides)
    )

    resolved = handle_google_credentials(
        None,
        env_var_names=[
            Environment.GOOGLE_DOCS_CREDENTIALS,
            Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
        ],
    )
    assert resolved == payload_docs


def test_handle_google_credentials_skips_null_env_values(monkeypatch):
    payload_slides = {"client_email": "slides@example.com", "private_key": "def"}
    monkeypatch.setenv(Environment.GOOGLE_DOCS_CREDENTIALS, "null")
    monkeypatch.setenv(
        Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, json.dumps(payload_slides)
    )

    resolved = handle_google_credentials(
        None,
        env_var_names=[
            Environment.GOOGLE_DOCS_CREDENTIALS,
            Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
        ],
    )
    assert resolved == payload_slides


def test_handle_google_credentials_validation_errors(tmp_path, monkeypatch):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not json}")

    with pytest.raises(AuthenticationError, match="not a valid JSON") as file_exc_info:
        handle_google_credentials(str(bad_path))
    assert isinstance(file_exc_info.value.__cause__, json.JSONDecodeError)

    with pytest.raises(AuthenticationError, match="not valid") as string_exc_info:
        handle_google_credentials("{broken")
    assert isinstance(string_exc_info.value.__cause__, json.JSONDecodeError)

    monkeypatch.delenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, raising=False)
    with pytest.raises(
        AuthenticationError, match="no supported credential environment variables"
    ):
        handle_google_credentials(None)


def test_load_google_credentials_from_env_external_account_json(monkeypatch):
    import google.auth

    calls = {}
    payload = {
        "type": "external_account",
        "audience": "//iam.googleapis.com/projects/123/locations/global",
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "token_url": "https://sts.googleapis.com/v1/token",
        "credential_source": {"file": "/tmp/token"},
    }
    monkeypatch.setenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, json.dumps(payload))

    def _load_from_dict(info, scopes=None, **kwargs):
        calls["info"] = info
        calls["scopes"] = scopes
        calls["kwargs"] = kwargs
        return "credentials", "project-from-json"

    monkeypatch.setattr(google.auth, "load_credentials_from_dict", _load_from_dict)

    result = load_google_credentials(
        None,
        scopes=["scope-a"],
    )

    assert result.credentials == "credentials"
    assert result.project_id == "project-from-json"
    assert result.source_type == "env_google_slideflow_credentials"
    assert result.source_name == Environment.GOOGLE_SLIDEFLOW_CREDENTIALS
    assert calls["info"]["type"] == "external_account"
    assert calls["scopes"] == ["scope-a"]


def test_load_google_credentials_rejects_external_account_from_provider_config(
    tmp_path, monkeypatch
):
    import google.auth

    payload = json.dumps({"type": "external_account", "audience": "repo-config"})
    monkeypatch.setattr(
        google.auth,
        "load_credentials_from_dict",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generic loader should not accept provider config")
        ),
    )

    with pytest.raises(AuthenticationError, match="Non-service-account"):
        load_google_credentials(payload, scopes=["scope-blocked"])

    creds_path = tmp_path / "external-account.json"
    creds_path.write_text(payload)
    with pytest.raises(AuthenticationError, match="Non-service-account"):
        load_google_credentials(str(creds_path), scopes=["scope-blocked"])


def test_load_google_credentials_uses_service_account_specific_loader(monkeypatch):
    import google.auth
    from google.oauth2 import service_account

    calls = {}

    class FakeCredentials:
        project_id = "project-from-credentials"

    def _from_service_account_info(info, scopes=None):
        calls["info"] = info
        calls["scopes"] = scopes
        return FakeCredentials()

    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_info",
        staticmethod(_from_service_account_info),
    )
    monkeypatch.setattr(
        google.auth,
        "load_credentials_from_dict",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generic loader should not be used for service accounts")
        ),
    )

    result = load_google_credentials(
        json.dumps(
            {
                "type": "service_account",
                "client_email": "svc@example.com",
                "project_id": "project-from-json",
            }
        ),
        scopes=["scope-sa"],
    )

    assert isinstance(result.credentials, FakeCredentials)
    assert result.project_id == "project-from-credentials"
    assert result.source_type == "explicit_json"
    assert calls["info"]["client_email"] == "svc@example.com"
    assert calls["scopes"] == ["scope-sa"]


def test_load_google_credentials_from_explicit_service_account_file(
    tmp_path, monkeypatch
):
    import google.auth
    from google.oauth2 import service_account

    creds_path = tmp_path / "service-account.json"
    creds_path.write_text(
        '{"type":"service_account","client_email":"svc@example.com","project_id":"file-project"}'
    )
    calls = {}

    class FakeCredentials:
        project_id = "file-project"

    def _from_service_account_info(info, scopes=None):
        calls["info"] = info
        calls["scopes"] = scopes
        return FakeCredentials()

    monkeypatch.setattr(
        service_account.Credentials,
        "from_service_account_info",
        staticmethod(_from_service_account_info),
    )
    monkeypatch.setattr(
        google.auth,
        "load_credentials_from_dict",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("generic loader should not be used for service accounts")
        ),
    )

    result = load_google_credentials(str(creds_path), scopes=["scope-b"])

    assert isinstance(result.credentials, FakeCredentials)
    assert result.source_type == "explicit_path"
    assert result.source_name == "provider.config.credentials"
    assert calls["info"]["client_email"] == "svc@example.com"
    assert calls["scopes"] == ["scope-b"]


def test_load_google_credentials_uses_provider_env_before_shared_env(monkeypatch):
    import google.auth

    docs_payload = {"type": "external_account", "audience": "docs"}
    shared_payload = {"type": "external_account", "audience": "shared"}
    calls = {}

    monkeypatch.setenv(Environment.GOOGLE_DOCS_CREDENTIALS, json.dumps(docs_payload))
    monkeypatch.setenv(
        Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, json.dumps(shared_payload)
    )

    def _load_from_dict(info, scopes=None, **kwargs):
        calls["info"] = info
        calls["scopes"] = scopes
        return "credentials", None

    monkeypatch.setattr(google.auth, "load_credentials_from_dict", _load_from_dict)

    result = load_google_credentials(
        None,
        scopes=["scope-c"],
        env_var_names=[
            Environment.GOOGLE_DOCS_CREDENTIALS,
            Environment.GOOGLE_SLIDEFLOW_CREDENTIALS,
        ],
    )

    assert calls["info"] == docs_payload
    assert calls["scopes"] == ["scope-c"]
    assert result.source_type == "env_google_docs_credentials"
    assert result.source_name == Environment.GOOGLE_DOCS_CREDENTIALS


def test_load_google_credentials_uses_google_application_credentials(
    tmp_path, monkeypatch
):
    import google.auth

    creds_path = tmp_path / "wif.json"
    creds_path.write_text('{"type":"external_account","audience":"gac"}')
    calls = {}
    monkeypatch.delenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, raising=False)
    monkeypatch.setenv(Environment.GOOGLE_APPLICATION_CREDENTIALS, str(creds_path))

    def _load_from_dict(info, scopes=None, **kwargs):
        calls["info"] = info
        calls["scopes"] = scopes
        return "credentials", "project-from-file"

    monkeypatch.setattr(google.auth, "load_credentials_from_dict", _load_from_dict)

    result = load_google_credentials(None, scopes=["scope-d"])

    assert result.credentials == "credentials"
    assert result.project_id == "project-from-file"
    assert result.source_type == "env_google_application_credentials"
    assert result.source_name == Environment.GOOGLE_APPLICATION_CREDENTIALS
    assert calls["info"]["audience"] == "gac"
    assert calls["scopes"] == ["scope-d"]


def test_load_google_credentials_falls_back_to_adc_default(monkeypatch):
    import google.auth

    calls = {}
    monkeypatch.delenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, raising=False)
    monkeypatch.delenv(Environment.GOOGLE_APPLICATION_CREDENTIALS, raising=False)

    def _default(scopes=None, **kwargs):
        calls["scopes"] = scopes
        calls["kwargs"] = kwargs
        return "credentials", "adc-project"

    monkeypatch.setattr(google.auth, "default", _default)

    result = load_google_credentials(None, scopes=["scope-e"])

    assert result.credentials == "credentials"
    assert result.project_id == "adc-project"
    assert result.source_type == "adc_default"
    assert result.source_name == "google.auth.default"
    assert calls["scopes"] == ["scope-e"]


def test_describe_google_credentials_source_reports_non_sensitive_source(
    tmp_path, monkeypatch
):
    creds_path = tmp_path / "creds.json"
    creds_path.write_text("{}")

    assert describe_google_credentials_source(str(creds_path)) == "explicit_path"
    assert describe_google_credentials_source("{}") == "explicit_json"

    monkeypatch.setenv(Environment.GOOGLE_DOCS_CREDENTIALS, "{}")
    assert (
        describe_google_credentials_source(
            None,
            [Environment.GOOGLE_DOCS_CREDENTIALS],
        )
        == "env_google_docs_credentials"
    )


def test_rate_limiter_validates_rates():
    with pytest.raises(ValueError, match="must be > 0"):
        rate_limiter_module.RateLimiter(0)
    with pytest.raises(ValueError, match="must be > 0"):
        rate_limiter_module.RateLimiter(-1)

    limiter = rate_limiter_module.RateLimiter(2.0)
    with pytest.raises(ValueError, match="must be > 0"):
        limiter.set_rate(0)


def test_rate_limiter_wait_sleeps_only_when_needed(monkeypatch):
    monotonic_values = iter([0.0, 0.6, 2.0])
    sleep_calls = []

    monkeypatch.setattr(
        rate_limiter_module.time, "monotonic", lambda: next(monotonic_values)
    )
    monkeypatch.setattr(
        rate_limiter_module.time, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    limiter = rate_limiter_module.RateLimiter(2.0)  # 0.5 seconds/request
    limiter.wait()  # sleeps 0.5
    limiter.wait()  # sleeps 0.4
    limiter.wait()  # no sleep

    assert sleep_calls == [0.5, 0.4]


def test_google_api_rate_limiter_shared_singleton_update():
    presentation_rate_limiter_module.reset_google_api_rate_limiter()

    rl1 = presentation_rate_limiter_module.get_google_api_rate_limiter(1.0)
    rl2 = presentation_rate_limiter_module.get_google_api_rate_limiter(3.0)
    rl3 = presentation_rate_limiter_module.get_google_api_rate_limiter(
        3.0, force_update=True
    )

    assert rl1 is rl2 is rl3
    assert rl3.rate == 3.0
