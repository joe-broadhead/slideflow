"""Property-based tests for data pipeline invariants."""

from __future__ import annotations

import string

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from slideflow.builtins.formatting.format import percentage, round_value
from slideflow.replacements.utils import dataframe_to_replacement_object
from slideflow.utilities.data_transforms import apply_data_transforms

_VALUE_STRATEGY = st.one_of(
    st.integers(min_value=-100_000, max_value=100_000),
    st.text(alphabet=string.ascii_letters + string.digits + " _-", max_size=20),
)
_PREFIX_STRATEGY = st.text(
    alphabet=string.ascii_letters + string.digits + "_", min_size=0, max_size=8
)


@settings(max_examples=100, deadline=None)
@given(data=st.data(), prefix=_PREFIX_STRATEGY)
def test_dataframe_to_replacement_object_rectangular_matrix(data, prefix: str) -> None:
    rows = data.draw(st.integers(min_value=1, max_value=5))
    cols = data.draw(st.integers(min_value=1, max_value=5))
    values = data.draw(
        st.lists(_VALUE_STRATEGY, min_size=rows * cols, max_size=rows * cols)
    )

    matrix = [values[row * cols : (row + 1) * cols] for row in range(rows)]
    df = pd.DataFrame(matrix)

    result = dataframe_to_replacement_object(df, prefix=prefix)

    assert len(result) == rows * cols
    for row_index in range(rows):
        for col_index in range(cols):
            placeholder = f"{{{{{prefix}{row_index + 1},{col_index + 1}}}}}"
            assert placeholder in result
            assert result[placeholder] == matrix[row_index][col_index]


@settings(max_examples=100, deadline=None)
@given(
    values=st.lists(
        st.integers(min_value=-10_000, max_value=10_000), min_size=1, max_size=50
    )
)
def test_apply_data_transforms_identity_preserves_values(values: list[int]) -> None:
    class _Frame:
        def __init__(self, data: list[int]):
            self.values = list(data)
            self.columns = ["value"]
            self.shape = (len(data), 1)

        @property
        def empty(self) -> bool:
            return len(self.values) == 0

        def copy(self):
            return _Frame(self.values)

    frame = _Frame(values)

    transformed = apply_data_transforms(
        [{"transform_fn": lambda df: df}],
        frame,
    )

    assert transformed is not frame
    assert transformed.values == frame.values
    assert transformed.values == values


@settings(max_examples=100, deadline=None)
@given(
    value=st.floats(
        allow_nan=False,
        allow_infinity=False,
        min_value=-1_000_000,
        max_value=1_000_000,
    ),
    ndigits=st.integers(min_value=0, max_value=4),
)
def test_formatters_remain_stable_for_numeric_inputs(
    value: float, ndigits: int
) -> None:
    assert round_value(value, ndigits=ndigits) == round(value, ndigits)
    assert (
        percentage(value, ndigits=ndigits, from_ratio=False) == f"{value:.{ndigits}f}%"
    )
