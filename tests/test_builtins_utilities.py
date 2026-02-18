import decimal

import pandas as pd
import pytest

import slideflow.builtins.registry as builtins_registry_module
import slideflow.builtins.formatting.format as format_module
from slideflow.builtins.column_utils import (
    abbreviate_currency_columns,
    abbreviate_number_columns,
    format_percentages,
    round_numbers,
)
from slideflow.builtins.formatting.color import function_registry as color_registry
from slideflow.builtins.formatting.color import green_or_red
from slideflow.builtins.table_utils import (
    create_dynamic_colors,
    create_growth_colors,
    create_performance_colors,
    create_traffic_light_colors,
    growth_color_function,
    performance_color_function,
)
from slideflow.utilities.exceptions import DataTransformError


def _install_pandas_stub_compat(monkeypatch):
    """Add minimal methods expected by transformation helpers."""
    df_type = type(pd.DataFrame({}))
    series_type = type(pd.DataFrame({"x": [1]})["x"])

    if not hasattr(df_type, "copy"):
        monkeypatch.setattr(df_type, "copy", lambda self: df_type(self), raising=False)

    if not hasattr(series_type, "round"):
        def _series_round(self, decimal_places=0):
            return series_type(
                round(float(value), decimal_places) if isinstance(value, (int, float)) else value
                for value in self
            )

        monkeypatch.setattr(series_type, "round", _series_round, raising=False)

    if not hasattr(series_type, "tolist"):
        monkeypatch.setattr(series_type, "tolist", lambda self: list(self), raising=False)


def test_formatting_functions_cover_numeric_and_edge_cases(monkeypatch):
    assert format_module.abbreviate(1234) == "1.2K"
    assert format_module.abbreviate(decimal.Decimal("42.5")) == "42.50"
    assert format_module.abbreviate("N/A") == "N/A"

    assert format_module.percentage(0.1234, ndigits=1) == "12.3%"
    assert format_module.percentage(25.5, from_ratio=False) == "25.50%"
    assert format_module.percentage(float("nan")) == "NaN%"
    assert format_module.percentage(None) == "None"

    assert format_module.round_value(3.14159, ndigits=3) == 3.142
    assert format_module.round_value("skip", ndigits=3) == "skip"

    assert format_module.format_currency(1234.5, currency_symbol="$") == "$1,234.50"
    assert (
        format_module.format_currency(
            -1234.5,
            currency_symbol="$",
            negative_parens=True,
            thousands_sep=".",
            decimal_sep=",",
        )
        == "($1.234,50)"
    )
    assert format_module.format_currency("not-a-number") == "not-a-number"

    assert format_module.abbreviate_currency(1_250_000, currency_symbol="$") == "$1.2M"
    assert (
        format_module.abbreviate_currency(-900, currency_symbol="$", negative_parens=True)
        == "($900.00)"
    )
    assert format_module.abbreviate_currency("n/a") == "n/a"

    assert set(format_module.function_registry) >= {
        "abbreviate",
        "percentage",
        "round_value",
        "format_currency",
        "abbreviate_currency",
    }

    # Force the hard-failure path in format_currency (unexpected conversion error).
    class BadFloat:
        def __float__(self):
            raise RuntimeError("boom")

    with pytest.raises(DataTransformError, match="Critical currency formatting error"):
        format_module.format_currency(BadFloat())

    # Force hard-failure path for percentage.
    monkeypatch.setattr(format_module.math, "isnan", lambda _v: (_ for _ in ()).throw(RuntimeError("err")))
    with pytest.raises(DataTransformError, match="Critical percentage formatting error"):
        format_module.percentage(1.23)


def test_color_and_table_helpers_generate_expected_color_maps(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    assert green_or_red(10) == "green"
    assert green_or_red(-1) == "red"
    assert green_or_red(decimal.Decimal("0")) == "green"
    assert green_or_red("x") == "black"
    assert color_registry["green_or_red"] is green_or_red

    assert growth_color_function(0) == "#28a745"
    assert growth_color_function(-0.1) == "#dc3545"
    assert growth_color_function("bad") == "black"

    assert performance_color_function(100, threshold=80) == "#28a745"
    assert performance_color_function(79.9, threshold=80) == "#dc3545"
    assert performance_color_function(None, threshold=80) == "black"

    assert create_traffic_light_colors(90, good_threshold=80, warning_threshold=60) == "#28a745"
    assert create_traffic_light_colors(70, good_threshold=80, warning_threshold=60) == "#ffc107"
    assert create_traffic_light_colors(50, good_threshold=80, warning_threshold=60) == "#dc3545"
    assert create_traffic_light_colors("x", good_threshold=80, warning_threshold=60) == "black"

    df = pd.DataFrame({"name": ["A", "B"], "growth": [0.2, -0.1], "score": [82, 75]})
    colored = create_dynamic_colors(
        df,
        column_order=["name", "growth", "score", "missing_col"],
        color_func=growth_color_function,
        target_columns=["growth", "missing_col"],
    )

    assert colored["_color_col_0"].tolist() == ["black", "black"]
    assert colored["_color_col_1"].tolist() == ["#28a745", "#dc3545"]
    assert colored["_color_col_2"].tolist() == ["black", "black"]
    assert colored["_color_col_3"].tolist() == ["black", "black"]

    growth_wrapped = create_growth_colors(df, ["name", "growth"], ["growth"])
    assert growth_wrapped["_color_col_1"].tolist() == ["#28a745", "#dc3545"]

    perf_wrapped = create_performance_colors(df, ["name", "score"], ["score"], threshold=80)
    assert perf_wrapped["_color_col_1"].tolist() == ["#28a745", "#dc3545"]


def test_column_transforms_apply_only_to_target_columns(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    original = pd.DataFrame(
        {
            "revenue": [1_250_000, 900],
            "cost": [400_000, 200],
            "ratio": [0.1234, -0.5],
            "value": [10.126, 20.555],
            "text": ["A", "B"],
        }
    )

    abbreviated = abbreviate_number_columns(original, ["revenue", "missing"])
    assert abbreviated["revenue"].tolist() == ["1.2M", "900.00"]
    assert original["revenue"].tolist() == [1_250_000, 900]  # original unchanged

    currency = abbreviate_currency_columns(
        original,
        ["cost"],
        currency_symbol="€",
        symbol_position="suffix",
        decimals=1,
    )
    assert currency["cost"].tolist() == ["400.0K €", "200.0 €"]

    percentages = format_percentages(original, ["ratio", "text"], decimal_places=1, from_ratio=True)
    assert percentages["ratio"].tolist() == ["12.3%", "-50.0%"]
    assert percentages["text"].tolist() == ["A", "B"]

    rounded = round_numbers(original, ["value", "missing"], decimal_places=2)
    assert rounded["value"].tolist() == [10.13, 20.55]


def test_builtins_registry_supports_custom_registration():
    known = builtins_registry_module.list_builtin_functions()
    assert "create_growth_colors" in known
    assert callable(builtins_registry_module.get_builtin_function("round_numbers"))

    custom_name = "__phase3_temp_builtin_fn__"

    def custom_fn(x):
        return f"custom:{x}"

    builtins_registry_module.register_builtin_function(custom_name, custom_fn)
    try:
        fetched = builtins_registry_module.get_builtin_function(custom_name)
        assert fetched("ok") == "custom:ok"
        assert custom_name in builtins_registry_module.list_builtin_functions()

        with pytest.raises(ValueError, match="already registered"):
            builtins_registry_module.register_builtin_function(custom_name, custom_fn)
    finally:
        builtins_registry_module.builtin_function_registry.remove(custom_name)
