import pandas as pd
import pytest

from slideflow.presentations.charts import PlotlyGraphObjects
from slideflow.utilities.exceptions import ChartGenerationError


def _chart() -> PlotlyGraphObjects:
    return PlotlyGraphObjects(type="plotly_go", traces=[{"type": "indicator"}])


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
