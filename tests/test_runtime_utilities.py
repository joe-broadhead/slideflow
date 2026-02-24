import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import pytest

import slideflow.utilities.rate_limiter as rate_limiter_module
from slideflow.constants import Environment
from slideflow.data.cache import DataSourceCache, get_data_cache
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import AuthenticationError
from slideflow.utilities.rate_limiter import RateLimiter


def test_data_source_cache_lifecycle_and_singleton_behavior():
    cache = get_data_cache()
    cache.enable()
    cache.clear()

    df = pd.DataFrame({"value": [1]})
    cache.set(df, source_type="csv", file_path="data.csv")

    assert cache.get("csv", file_path="data.csv") is df
    assert cache.size == 1
    assert cache.is_enabled is True
    assert get_data_cache() is cache

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
    cache = DataSourceCache()
    key_a = cache._generate_key("databricks", query="select 1", target="prod")
    key_b = cache._generate_key("databricks", target="prod", query="select 1")
    assert key_a == key_b


def test_data_source_cache_key_generation_is_order_stable_for_nested_values():
    cache = DataSourceCache()
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


def test_data_source_cache_enforces_lru_entry_cap(monkeypatch):
    monkeypatch.setenv(Environment.SLIDEFLOW_DATA_CACHE_MAX_ENTRIES, "2")
    cache = get_data_cache()
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
        assert cache.get("csv", file_path="a.csv") is df_a

        cache.set(df_c, source_type="csv", file_path="c.csv")
        assert cache.size == 2
        assert cache.get("csv", file_path="a.csv") is df_a
        assert cache.get("csv", file_path="b.csv") is None
        assert cache.get("csv", file_path="c.csv") is df_c
    finally:
        cache._max_entries = original_max_entries
        cache.clear()


def test_data_source_cache_singleton_init_is_thread_safe():
    DataSourceCache._instance = None

    def create_cache_instance_id() -> int:
        return id(DataSourceCache())

    with ThreadPoolExecutor(max_workers=16) as executor:
        instance_ids = list(
            executor.map(lambda _i: create_cache_instance_id(), range(64))
        )

    assert len(set(instance_ids)) == 1


def test_data_source_cache_invalid_env_max_entries_falls_back(monkeypatch):
    monkeypatch.setenv(Environment.SLIDEFLOW_DATA_CACHE_MAX_ENTRIES, "not-an-int")
    cache = get_data_cache()
    cache.enable()
    assert cache.max_entries > 0


def test_data_source_cache_get_or_load_deduplicates_concurrent_loads():
    cache = get_data_cache()
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
    assert all(result is expected_df for result in results)

    cache.clear()


def test_data_source_cache_get_or_load_unblocks_waiters_on_base_exception():
    cache = get_data_cache()
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
    assert data_results[0] is expected_df
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


def test_handle_google_credentials_validation_errors(tmp_path, monkeypatch):
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not json}")

    with pytest.raises(AuthenticationError, match="not a valid JSON"):
        handle_google_credentials(str(bad_path))

    with pytest.raises(AuthenticationError, match="not valid"):
        handle_google_credentials("{broken")

    monkeypatch.delenv(Environment.GOOGLE_SLIDEFLOW_CREDENTIALS, raising=False)
    with pytest.raises(AuthenticationError, match="Credentials not provided"):
        handle_google_credentials(None)


def test_rate_limiter_validates_rates():
    with pytest.raises(ValueError, match="must be > 0"):
        RateLimiter(0)
    with pytest.raises(ValueError, match="must be > 0"):
        RateLimiter(-1)

    limiter = RateLimiter(2.0)
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

    limiter = RateLimiter(2.0)  # 0.5 seconds/request
    limiter.wait()  # sleeps 0.5
    limiter.wait()  # sleeps 0.4
    limiter.wait()  # no sleep

    assert sleep_calls == [0.5, 0.4]
