import pandas as pd
import pytest

import slideflow.replacements.ai_text as ai_text_module
from slideflow.replacements.ai_text import AITextReplacement
from slideflow.replacements.table import (
    TableColumnFormatter,
    TableFormattingOptions,
    TableReplacement,
)
from slideflow.replacements.text import TextReplacement
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.utilities.exceptions import DataTransformError, ReplacementError


def _install_pandas_stub_compat(monkeypatch):
    """Provide minimal pandas methods/properties used by transform/replacement code."""
    df_type = type(pd.DataFrame({}))
    series_type = type(pd.DataFrame({"x": [1]})["x"])

    if not hasattr(df_type, "copy"):
        monkeypatch.setattr(df_type, "copy", lambda self: df_type(self), raising=False)
    if not hasattr(df_type, "empty"):
        monkeypatch.setattr(
            df_type, "empty", property(lambda self: len(self) == 0), raising=False
        )
    if not hasattr(df_type, "shape"):
        monkeypatch.setattr(
            df_type,
            "shape",
            property(lambda self: (len(self), len(self.columns))),
            raising=False,
        )
    if not hasattr(series_type, "tolist"):
        monkeypatch.setattr(
            series_type, "tolist", lambda self: list(self), raising=False
        )


def test_apply_data_transforms_noop_success_and_failure_paths(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    df = pd.DataFrame({"a": [1, 2]})

    assert apply_data_transforms(None, df) is df
    assert apply_data_transforms([], df) is df

    empty_df = pd.DataFrame({})
    assert apply_data_transforms([{"transform_fn": lambda x: x}], empty_df) is empty_df

    def add_scaled_column(frame, multiplier=2):
        frame["b"] = [value * multiplier for value in frame["a"]]
        return frame

    transformed = apply_data_transforms(
        [{"transform_fn": add_scaled_column, "transform_args": {"multiplier": 3}}],
        df,
    )
    assert transformed["b"].tolist() == [3, 6]
    assert "b" not in df.columns  # original should be untouched

    def explode(_frame, column):
        raise KeyError(column)

    with pytest.raises(DataTransformError, match="Transform function 'explode' failed"):
        apply_data_transforms(
            [{"transform_fn": explode, "transform_args": {"column": "missing"}}],
            df,
        )


def test_text_replacement_static_and_value_function_modes(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    static = TextReplacement(type="text", placeholder="{{STATIC}}", replacement=123)
    assert static.replacement == "123"
    assert static.get_replacement() == "123"

    empty = TextReplacement(type="text", placeholder="{{EMPTY}}")
    assert empty.get_replacement() == ""

    direct_fn = TextReplacement(
        type="text",
        placeholder="{{FN}}",
        value_fn=lambda greeting="hi": f"{greeting} there",
        value_fn_args={"greeting": "hello"},
    )
    assert direct_fn.get_replacement() == "hello there"

    class DummySource:
        def fetch_data(self):
            return pd.DataFrame({"v": [10, 20]})

    def add_column(frame):
        frame["w"] = [value + 1 for value in frame["v"]]
        return frame

    from_data = TextReplacement.model_construct(
        type="text",
        placeholder="{{DATA}}",
        replacement=None,
        data_source=DummySource(),
        value_fn=lambda frame, suffix="": f"{len(frame.columns)}{suffix}",
        value_fn_args={"suffix": "c"},
        data_transforms=[{"transform_fn": add_column}],
    )
    assert from_data.get_replacement() == "2c"


def test_table_replacement_dynamic_mode_applies_transforms_and_formatters(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    class DummySource:
        def fetch_data(self):
            return pd.DataFrame({"product": ["Widget"], "sales": [1000]})

    def double_sales(frame):
        frame["sales"] = [value * 2 for value in frame["sales"]]
        return frame

    formatting = TableFormattingOptions(
        custom_formatters={
            "sales": TableColumnFormatter(
                format_fn=lambda value, symbol="$": f"{symbol}{value}",
                format_fn_args={"symbol": "EUR "},
            )
        }
    )

    replacement = TableReplacement.model_construct(
        type="table",
        prefix="T_",
        data_source=DummySource(),
        formatting=formatting,
        replacements=None,
        data_transforms=[{"transform_fn": double_sales}],
    )

    output = replacement.get_replacement()
    assert output == {
        "{{T_1,1}}": "Widget",
        "{{T_1,2}}": "EUR 2000",
    }


def test_ai_text_replacement_provider_resolution_and_prompt_context(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    class DummyProvider:
        def __init__(self, api_key=None):
            self.api_key = api_key

        def generate_text(self, prompt, temperature=0.0):
            return f"{self.api_key}:{temperature}:{prompt}"

    monkeypatch.setattr(
        ai_text_module, "get_provider_class", lambda _name: DummyProvider
    )

    string_provider = AITextReplacement(
        type="ai_text",
        placeholder="{{AI}}",
        prompt="Prompt",
        provider="dummy",
        provider_args={"api_key": "k", "temperature": 0.4},
    )
    fn, call_args = string_provider._prepare_provider()
    assert call_args == {"temperature": 0.4}
    assert fn("hello", **call_args).startswith("k:0.4:hello")

    instance_provider = AITextReplacement(
        type="ai_text",
        placeholder="{{AI2}}",
        prompt="Prompt",
        provider=DummyProvider(api_key="instance"),
        provider_args={"temperature": 0.2},
    )
    fn2, call_args2 = instance_provider._prepare_provider()
    assert fn2("hello", **call_args2).startswith("instance:0.2:hello")

    callable_provider = AITextReplacement(
        type="ai_text",
        placeholder="{{AI3}}",
        prompt="Prompt",
        provider=lambda prompt, suffix="": f"{prompt}{suffix}",
        provider_args={"suffix": "!"},
    )
    fn3, call_args3 = callable_provider._prepare_provider()
    assert fn3("hello", **call_args3) == "hello!"

    invalid_provider = AITextReplacement.model_construct(
        type="ai_text",
        placeholder="{{BAD}}",
        prompt="Prompt",
        provider=123,
        provider_args={},
        data_source=None,
        data_transforms=None,
    )
    with pytest.raises(ReplacementError, match="Invalid AI provider"):
        invalid_provider._prepare_provider()


def test_ai_text_replacement_data_context_and_transform_failure_fallback(monkeypatch):
    _install_pandas_stub_compat(monkeypatch)

    class DummySource:
        def __init__(self, name):
            self.name = name

        def fetch_data(self):
            return pd.DataFrame({"metric": [42]})

    ok = AITextReplacement.model_construct(
        type="ai_text",
        placeholder="{{AI_OK}}",
        prompt="Summarize",
        provider=lambda prompt, suffix="": f"{prompt}{suffix}",
        provider_args={"suffix": "!"},
        data_source=[DummySource("sales")],
        data_transforms=[{"transform_fn": lambda frame: frame}],
    )
    rendered = ok.get_replacement()
    assert "Summarize" in rendered
    assert "Data from sales" in rendered
    assert rendered.endswith("!")

    def fail_transform(_frame):
        raise RuntimeError("boom")

    failing = AITextReplacement.model_construct(
        type="ai_text",
        placeholder="{{AI_FAIL}}",
        prompt="Summarize",
        provider=lambda prompt, **_kwargs: prompt,
        provider_args={},
        data_source=[DummySource("sales")],
        data_transforms=[{"transform_fn": fail_transform}],
    )
    assert (
        failing.get_replacement()
        == 'Summary unable to be generated as data source "sales" was not available'
    )
