import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
from typing import ClassVar, Literal, Type

import pandas as pd
import pytest
from pydantic import Field, ValidationError

from slideflow.cli.commands.sheets import _runtime_controls_payload
from slideflow.data.connectors.base import BaseSourceConfig, DataConnector
from slideflow.runtime import (
    BuildRuntimeContext,
    QueryConcurrencyController,
    RuntimeConfig,
)


def test_runtime_config_defaults_and_validates_positive_strict_integer():
    assert RuntimeConfig().query_threads == 10
    assert RuntimeConfig(query_threads=4).query_threads == 4
    for invalid in (0, -1, 1.5, "4", True):
        with pytest.raises(ValidationError):
            RuntimeConfig(query_threads=invalid)


def test_query_controller_enforces_limit_and_releases_after_failure():
    controller = QueryConcurrencyController(2)
    lock = threading.Lock()
    active = 0
    peak = 0

    def worker(index: int) -> None:
        nonlocal active, peak
        try:
            with controller.permit("fake"):
                with lock:
                    active += 1
                    peak = max(peak, active)
                try:
                    time.sleep(0.01)
                    if index == 0:
                        raise RuntimeError("expected")
                finally:
                    with lock:
                        active -= 1
        except RuntimeError:
            pass

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(worker, range(8)))

    assert peak == 2
    with controller.permit("fake"):
        pass


def test_sheets_runtime_query_precedence_and_payload():
    workbook_config = SimpleNamespace(
        runtime=RuntimeConfig(query_threads=4),
        provider=SimpleNamespace(config={}),
        workbook=SimpleNamespace(tabs=[object(), object()]),
    )
    configured, _ = _runtime_controls_payload(
        workbook_config, threads=None, requests_per_second=None
    )
    assert configured["query_threads"] == {
        "requested": 4,
        "applied": 4,
        "source": "config",
        "scope": "process",
    }

    overridden, _ = _runtime_controls_payload(
        workbook_config,
        threads=None,
        requests_per_second=None,
        query_threads=2,
    )
    assert overridden["query_threads"] == {
        "requested": 2,
        "applied": 2,
        "source": "cli_override",
        "scope": "process",
    }


def test_data_cache_hits_do_not_consume_query_permits():
    class ProbeController:
        limit = 1
        calls = 0

        @contextmanager
        def permit(self, _backend):
            self.calls += 1
            yield

    class WarehouseConnector(DataConnector):
        def fetch_data(self):
            with self.warehouse_query_permit("fake"):
                return pd.DataFrame({"value": [1]})

    class WarehouseSource(BaseSourceConfig):
        type: Literal["runtime_test"] = Field("runtime_test")
        connector_class: ClassVar[Type[DataConnector]] = WarehouseConnector

    controller = ProbeController()
    source = WarehouseSource(name="cached")
    source.bind_runtime_context(BuildRuntimeContext(query_controller=controller))
    source.fetch_data()
    source.fetch_data()

    assert controller.calls == 1
