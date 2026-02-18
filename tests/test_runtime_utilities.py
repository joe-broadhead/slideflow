import json

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
