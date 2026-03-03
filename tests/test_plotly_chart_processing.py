import sys
import types

import pandas as pd
import pytest

import slideflow.presentations.charts as charts_module
from slideflow.utilities.exceptions import ChartGenerationError


def _chart() -> charts_module.PlotlyGraphObjects:
    return charts_module.PlotlyGraphObjects(
        type="plotly_go", traces=[{"type": "indicator"}]
    )


def test_process_trace_config_column_reference_with_index_returns_scalar():
    chart = _chart()
    df = pd.DataFrame({"metric": [123.4, 150.0]})

    processed = chart._process_trace_config({"value": "$metric[0]"}, df)

    assert processed["value"] == 123.4


def test_process_trace_config_column_reference_with_negative_index_returns_scalar():
    chart = _chart()
    df = pd.DataFrame({"metric": [123.4, 150.0]})

    processed = chart._process_trace_config({"value": "$metric[-1]"}, df)

    assert processed["value"] == 150.0


def test_process_trace_config_column_reference_without_index_remains_list():
    chart = _chart()
    df = pd.DataFrame({"metric": [123.4, 150.0]})

    processed = chart._process_trace_config({"value": "$metric"}, df)

    assert processed["value"] == [123.4, 150.0]


def test_process_trace_config_column_reference_index_out_of_range_raises():
    chart = _chart()
    df = pd.DataFrame({"metric": [123.4]})

    with pytest.raises(ChartGenerationError, match="out of range"):
        chart._process_trace_config({"value": "$metric[3]"}, df)


def test_process_trace_config_empty_df_replaces_list_column_refs_with_empty_values():
    chart = _chart()
    df = pd.DataFrame(
        {"metric_a": [], "metric_b": [], "_color_col_0": [], "_color_col_1": []}
    )

    processed = chart._process_trace_config(
        {
            "cells": {
                "values": ["$metric_a", "$metric_b"],
                "font": {"color": ["$_color_col_0", "$_color_col_1"]},
                "meta": ["$metric_a[0]"],
            }
        },
        df,
    )

    assert processed["cells"]["values"] == [[], []]
    assert processed["cells"]["font"]["color"] == [[], []]
    assert processed["cells"]["meta"] == [None]


class _FakeFigure:
    def to_plotly_json(self):
        return {"data": [], "layout": {}}


def test_plotly_to_image_prefers_headless_kaleido(monkeypatch):
    calls = {}

    def _start_sync_server(**kwargs):
        calls["start_kwargs"] = kwargs

    def _calc_fig_sync(fig_dict, opts=None, kopts=None):
        calls["fig_dict"] = fig_dict
        calls["opts"] = opts
        calls["kopts"] = kopts
        return b"kaleido-bytes"

    fake_kaleido = types.SimpleNamespace(
        start_sync_server=_start_sync_server,
        calc_fig_sync=_calc_fig_sync,
    )
    monkeypatch.setitem(sys.modules, "kaleido", fake_kaleido)

    image = charts_module._plotly_to_image(_FakeFigure(), "png", 640, 360, 2.0)

    assert image == b"kaleido-bytes"
    assert calls["start_kwargs"] == {
        "n": 1,
        "timeout": 90,
        "headless": True,
        "silence_warnings": True,
    }
    assert calls["fig_dict"] == {"data": [], "layout": {}}
    assert calls["opts"] == {"format": "png", "width": 640, "height": 360, "scale": 2.0}
    assert calls["kopts"] is None


def test_plotly_to_image_falls_back_to_plotly_io_on_kaleido_error(monkeypatch):
    def _start_sync_server(**kwargs):
        return None

    def _raise_kaleido(*args, **kwargs):
        raise RuntimeError("kaleido unavailable")

    fake_kaleido = types.SimpleNamespace(
        start_sync_server=_start_sync_server,
        calc_fig_sync=_raise_kaleido,
    )
    monkeypatch.setitem(sys.modules, "kaleido", fake_kaleido)

    fallback_calls = {}

    def _fallback(fig, format, width, height, scale):
        fallback_calls["format"] = format
        fallback_calls["width"] = width
        fallback_calls["height"] = height
        fallback_calls["scale"] = scale
        return b"plotly-bytes"

    monkeypatch.setattr(charts_module.pio, "to_image", _fallback)

    image = charts_module._plotly_to_image(_FakeFigure(), "png", 320, 180, 1.0)

    assert image == b"plotly-bytes"
    assert fallback_calls == {
        "format": "png",
        "width": 320,
        "height": 180,
        "scale": 1.0,
    }
