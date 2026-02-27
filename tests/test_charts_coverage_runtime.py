from __future__ import annotations

from concurrent.futures import TimeoutError
from types import SimpleNamespace
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
import pytest

import slideflow.presentations.charts as charts_module
from slideflow.constants import GoogleSlides, Timing
from slideflow.utilities.exceptions import ChartGenerationError


class _MinimalChart(charts_module.BaseChart):
    type: Literal["minimal"] = "minimal"

    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        return b"image-bytes"


def test_reset_chart_export_executor_terminates_processes_and_shutdowns():
    class _Process:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    class _Executor:
        def __init__(self) -> None:
            self._processes = {"a": _Process(), "b": _Process()}
            self.shutdown_calls: List[Dict[str, Any]] = []

        def shutdown(self, wait: bool, cancel_futures: bool) -> None:
            self.shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})

    executor = _Executor()
    charts_module._CHART_EXPORT_EXECUTOR = executor

    charts_module._reset_chart_export_executor()

    assert charts_module._CHART_EXPORT_EXECUTOR is None
    assert all(process.terminated for process in executor._processes.values())
    assert executor.shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_reset_chart_export_executor_handles_terminate_and_shutdown_errors():
    class _Process:
        def terminate(self) -> None:
            raise RuntimeError("terminate failed")

    class _Executor:
        _processes = {"bad": _Process()}

        def shutdown(self, wait: bool, cancel_futures: bool) -> None:
            raise RuntimeError("shutdown failed")

    charts_module._CHART_EXPORT_EXECUTOR = _Executor()

    charts_module._reset_chart_export_executor()

    assert charts_module._CHART_EXPORT_EXECUTOR is None


def test_execute_with_retry_timeout_then_success(monkeypatch):
    class _FutureTimeout:
        def result(self, timeout: int) -> bytes:
            raise TimeoutError()

    class _FutureSuccess:
        def result(self, timeout: int) -> bytes:
            return b"ok"

    class _Executor:
        def __init__(self, future: Any) -> None:
            self._future = future

        def submit(self, func, *args, **kwargs):
            return self._future

    executors = iter([_Executor(_FutureTimeout()), _Executor(_FutureSuccess())])
    reset_calls: List[bool] = []
    monkeypatch.setattr(
        charts_module, "_get_chart_export_executor", lambda: next(executors)
    )
    monkeypatch.setattr(
        charts_module, "_reset_chart_export_executor", lambda: reset_calls.append(True)
    )

    result = charts_module._execute_with_retry(lambda: b"unused")

    assert result == b"ok"
    assert reset_calls == [True]


def test_execute_with_retry_resets_and_reraises_non_timeout(monkeypatch):
    class _FutureError:
        def result(self, timeout: int) -> bytes:
            raise RuntimeError("boom")

    class _Executor:
        def submit(self, func, *args, **kwargs):
            return _FutureError()

    reset_calls: List[bool] = []
    monkeypatch.setattr(
        charts_module, "_get_chart_export_executor", lambda: _Executor()
    )
    monkeypatch.setattr(
        charts_module, "_reset_chart_export_executor", lambda: reset_calls.append(True)
    )

    with pytest.raises(RuntimeError, match="boom"):
        charts_module._execute_with_retry(lambda: b"unused")

    assert reset_calls == [True]


def test_execute_with_retry_raises_after_all_timeouts(monkeypatch):
    class _FutureTimeout:
        def result(self, timeout: int) -> bytes:
            raise TimeoutError()

    class _Executor:
        def submit(self, func, *args, **kwargs):
            return _FutureTimeout()

    reset_calls: List[bool] = []
    monkeypatch.setattr(
        charts_module, "_get_chart_export_executor", lambda: _Executor()
    )
    monkeypatch.setattr(
        charts_module, "_reset_chart_export_executor", lambda: reset_calls.append(True)
    )

    with pytest.raises(ChartGenerationError, match="failed after all retries"):
        charts_module._execute_with_retry(lambda: b"unused")

    assert reset_calls == [True, True, True]


def test_execute_with_retry_uses_configured_timeout_sequence(monkeypatch):
    class _FutureTimeout:
        def __init__(self) -> None:
            self.timeouts: List[int] = []

        def result(self, timeout: int) -> bytes:
            self.timeouts.append(timeout)
            raise TimeoutError()

    class _Executor:
        def __init__(self, future: _FutureTimeout) -> None:
            self.future = future

        def submit(self, func, *args, **kwargs):
            return self.future

    future = _FutureTimeout()
    executor = _Executor(future)
    reset_calls: List[bool] = []

    monkeypatch.setattr(
        charts_module,
        "_get_chart_export_executor",
        lambda: executor,
    )
    monkeypatch.setattr(
        charts_module, "_reset_chart_export_executor", lambda: reset_calls.append(True)
    )
    monkeypatch.setattr(
        charts_module.Timing,
        "CHART_EXPORT_RETRY_TIMEOUTS_S",
        (1, 2, 3),
    )

    with pytest.raises(ChartGenerationError, match="failed after all retries"):
        charts_module._execute_with_retry(lambda: b"unused")

    assert future.timeouts == [1, 2, 3]
    assert reset_calls == [True, True, True]


def test_plotly_to_image_without_scale_omits_scale_option(monkeypatch):
    calls: Dict[str, Any] = {}

    class _FakeFigure:
        def to_plotly_json(self):
            return {"data": [], "layout": {}}

    class _Kaleido:
        @staticmethod
        def start_sync_server(**kwargs):
            calls["server_kwargs"] = kwargs

        @staticmethod
        def calc_fig_sync(fig_json, opts=None):
            calls["fig_json"] = fig_json
            calls["opts"] = opts
            return b"ok"

    monkeypatch.setitem(__import__("sys").modules, "kaleido", _Kaleido)

    rendered = charts_module._plotly_to_image(_FakeFigure(), "png", 200, 100, None)

    assert rendered == b"ok"
    assert calls["opts"] == {"format": "png", "width": 200, "height": 100}
    assert (
        calls["server_kwargs"]["timeout"] == Timing.CHART_EXPORT_KALEIDO_START_TIMEOUT_S
    )


def test_base_chart_validation_fetch_transform_and_upload(monkeypatch):
    chart = _MinimalChart(type="minimal", title="My Chart")

    with pytest.raises(ChartGenerationError, match="dimensions_format must be"):
        _MinimalChart(type="minimal", dimensions_format="pixels")
    with pytest.raises(ChartGenerationError, match="horizontal-vertical"):
        _MinimalChart(type="minimal", alignment_format="center")
    with pytest.raises(ChartGenerationError, match="horizontal alignment must be"):
        _MinimalChart(type="minimal", alignment_format="middle-top")
    with pytest.raises(ChartGenerationError, match="vertical alignment must be"):
        _MinimalChart(type="minimal", alignment_format="left-middle")

    class _Source:
        def fetch_data(self):
            return pd.DataFrame({"x": [1]})

    chart.data_source = _Source()  # type: ignore[assignment]
    fetched = chart.fetch_data()
    assert isinstance(fetched, pd.DataFrame)
    assert list(fetched["x"]) == [1]

    monkeypatch.setattr(
        charts_module,
        "apply_data_transforms",
        lambda transforms, df: pd.DataFrame({"x": [1], "y": [2]}),
    )
    transformed = chart.apply_data_transforms(pd.DataFrame({"x": [1]}))
    assert list(transformed["y"]) == [2]

    wait_calls: List[int] = []

    class _Limiter:
        def wait(self) -> None:
            wait_calls.append(1)

    monkeypatch.setattr(charts_module, "_get_rate_limiter", lambda _rps: _Limiter())
    monkeypatch.setattr(charts_module.uuid, "uuid4", lambda: type("U", (), {"hex": "abc12345dead"})())  # type: ignore[misc]

    class _Request:
        def __init__(self, response: Dict[str, Any]) -> None:
            self.response = response
            self.retries: List[Optional[int]] = []

        def execute(self, num_retries: Optional[int] = None):
            self.retries.append(num_retries)
            return self.response

    file_create_request = _Request({"id": "file-1"})
    permission_request = _Request({})

    class _Files:
        def __init__(self) -> None:
            self.create_calls: List[Dict[str, Any]] = []

        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            return file_create_request

    class _Permissions:
        def __init__(self) -> None:
            self.create_calls: List[Dict[str, Any]] = []

        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            return permission_request

    files_api = _Files()
    permissions_api = _Permissions()
    drive_service = type(
        "DriveService",
        (),
        {
            "files": lambda self: files_api,
            "permissions": lambda self: permissions_api,
        },
    )()

    public_url, file_id = chart._upload_to_drive(b"bytes", drive_service)

    assert public_url == "https://drive.google.com/uc?id=file-1"
    assert file_id == "file-1"
    assert file_create_request.retries == [3]
    assert permission_request.retries == [3]
    assert len(wait_calls) == 2


def test_generate_public_url_uses_empty_dataframe_when_no_source(monkeypatch):
    class _ObservedChart(_MinimalChart):
        seen_df: Optional[pd.DataFrame] = None

        def generate_chart_image(self, df: pd.DataFrame) -> bytes:
            self.seen_df = df
            return b"img"

    chart = _ObservedChart(type="minimal", title="Observed")
    monkeypatch.setattr(chart, "_upload_to_drive", lambda image, _svc: ("url", "fid"))

    url, file_id = chart.generate_public_url(drive_service=object())

    assert (url, file_id) == ("url", "fid")
    assert isinstance(chart.seen_df, pd.DataFrame)
    assert len(chart.seen_df) == 0


def test_plotly_generate_chart_image_evaluates_expressions_and_scale(monkeypatch):
    trace_calls: List[Dict[str, Any]] = []
    layout_calls: List[Dict[str, Any]] = []
    retry_calls: List[Any] = []

    class _FakeTrace:
        def __init__(self, **kwargs) -> None:
            trace_calls.append(kwargs)

    class _FakeFigure:
        def add_trace(self, trace) -> None:
            return None

        def update_layout(self, **kwargs) -> None:
            layout_calls.append(kwargs)

    monkeypatch.setattr(
        charts_module,
        "go",
        type("GO", (), {"Figure": _FakeFigure, "Bar": _FakeTrace}),
    )
    monkeypatch.setattr(charts_module, "safe_eval_expression", lambda expr: 150 if "width" in expr else 90)  # type: ignore[arg-type]
    monkeypatch.setattr(
        charts_module,
        "_execute_with_retry",
        lambda func, fig, fmt, width, height, scale: retry_calls.append(
            (func, fmt, width, height, scale)
        )
        or b"rendered",
    )

    chart = charts_module.PlotlyGraphObjects(
        type="plotly_go",
        title="Demo",
        width="width_expr",
        height="height_expr",
        traces=[{"type": "bar", "x": [1], "y": [2]}],
        layout_config={"showlegend": False},
        scale=1.5,
    )

    rendered = chart.generate_chart_image(pd.DataFrame())

    expected_width = int(150 * GoogleSlides.POINTS_TO_PIXELS_RATIO)
    expected_height = int(90 * GoogleSlides.POINTS_TO_PIXELS_RATIO)

    assert rendered == b"rendered"
    assert trace_calls == [{"x": [1], "y": [2]}]
    assert {"showlegend": False} in layout_calls
    assert any(call.get("title") == "Demo" for call in layout_calls)
    assert retry_calls[0][1:] == ("png", expected_width, expected_height, 1.5)


def test_plotly_trace_config_invalid_index_token_raises_missing_column():
    chart = charts_module.PlotlyGraphObjects(type="plotly_go", traces=[])
    df = pd.DataFrame({"metric": [1, 2]})

    with pytest.raises(
        ChartGenerationError, match="Column 'metric\\[bad\\]' not found"
    ):
        chart._process_trace_config({"value": "$metric[bad]"}, df)


def test_custom_chart_process_config_and_generate(monkeypatch):
    captured: Dict[str, Any] = {}

    def _chart_fn(df: pd.DataFrame, config: Dict[str, Any], _chart) -> bytes:
        captured["df_columns"] = list(df.columns)
        captured["config"] = config
        return b"custom-bytes"

    chart = charts_module.CustomChart(
        type="custom",
        title="Custom Title",
        chart_fn=_chart_fn,
        chart_config={
            "series": "$value",
            "nested": {"inner": "$value"},
            "labels": ["$value", "literal"],
        },
    )

    output = chart.generate_chart_image(pd.DataFrame({"value": [10, 20]}))

    assert output == b"custom-bytes"
    assert captured["df_columns"] == ["value"]
    assert list(captured["config"]["series"]) == [10, 20]
    assert list(captured["config"]["nested"]["inner"]) == [10, 20]
    assert list(captured["config"]["labels"][0]) == [10, 20]
    assert captured["config"]["labels"][1] == "literal"
    assert captured["config"]["title"] == "Custom Title"


def test_custom_chart_process_config_missing_column_raises():
    chart = charts_module.CustomChart(
        type="custom", chart_fn=lambda *_: b"", chart_config={}
    )
    fake_df = SimpleNamespace(columns=["x"], empty=False, shape=(1, 1))

    with pytest.raises(ChartGenerationError, match="Column 'missing' not found"):
        chart._process_config({"value": "$missing"}, fake_df)


def test_template_chart_renders_and_combines_transforms(monkeypatch):
    captured: Dict[str, Any] = {}

    class _Engine:
        def render_template(self, template_name: str, template_config: Dict[str, Any]):
            captured["template_name"] = template_name
            captured["template_config"] = template_config
            return {
                "traces": [{"type": "bar", "x": [1], "y": [2]}],
                "layout_config": {"showlegend": False},
                "data_transforms": [{"type": "template_transform"}],
            }

    class _FakePlotlyChart:
        def __init__(self, **kwargs):
            captured["plotly_kwargs"] = kwargs

        def generate_chart_image(self, df: pd.DataFrame) -> bytes:
            captured["df_rows"] = len(df)
            captured["df_columns"] = list(df.columns)
            return b"template-bytes"

    monkeypatch.setattr(charts_module, "get_template_engine", lambda: _Engine())
    monkeypatch.setattr(charts_module, "PlotlyGraphObjects", _FakePlotlyChart)

    chart = charts_module.TemplateChart(
        type="template",
        title="Template Title",
        template_name="my_template",
        template_config={"region": "EU"},
        data_transforms=[{"type": "user_transform"}],
        width=420,
        height=315,
        x=10,
        y=20,
    )

    output = chart.generate_chart_image(pd.DataFrame({"a": [1]}))

    assert output == b"template-bytes"
    assert captured["template_name"] == "my_template"
    assert captured["template_config"] == {"region": "EU"}
    assert captured["plotly_kwargs"]["title"] == "Template Title"
    assert captured["plotly_kwargs"]["traces"] == [{"type": "bar", "x": [1], "y": [2]}]
    assert captured["plotly_kwargs"]["data_transforms"] == [
        {"type": "user_transform"},
        {"type": "template_transform"},
    ]
    assert captured["df_rows"] == 1
    assert captured["df_columns"] == ["a"]
