from __future__ import annotations

import pandas as pd

from slideflow.replacements.utils import dataframe_to_replacement_object


def test_dataframe_to_replacement_object_uses_1_based_coordinates_and_prefix():
    df = pd.DataFrame(
        {
            "Name": ["alpha", "beta"],
            "Value": [10, 20],
        }
    )

    result = dataframe_to_replacement_object(df, prefix="ITEM_")

    assert result == {
        "{{ITEM_1,1}}": "alpha",
        "{{ITEM_1,2}}": 10,
        "{{ITEM_2,1}}": "beta",
        "{{ITEM_2,2}}": 20,
    }


def test_dataframe_to_replacement_object_returns_empty_dict_for_empty_dataframe():
    df = pd.DataFrame()
    assert dataframe_to_replacement_object(df, prefix="EMPTY_") == {}


def test_dataframe_to_replacement_object_preserves_values_without_header_row():
    df = pd.DataFrame({"A": ["x"], "B": ["y"]})
    result = dataframe_to_replacement_object(df)

    assert "{{1,1}}" in result
    assert "{{1,2}}" in result
    assert "{{2,1}}" not in result
    assert result["{{1,1}}"] == "x"
    assert result["{{1,2}}"] == "y"
