import pandas as pd

from slideflow.replacements.utils import dataframe_to_replacement_object


def test_dataframe_to_replacement_object_uses_values_not_headers():
    df = pd.DataFrame(
        {
            "Quarter": ["Q1", "Q2"],
            "Revenue": [100, 120],
        }
    )

    assert dataframe_to_replacement_object(df, "SALES_") == {
        "{{SALES_1,1}}": "Q1",
        "{{SALES_1,2}}": 100,
        "{{SALES_2,1}}": "Q2",
        "{{SALES_2,2}}": 120,
    }


def test_dataframe_to_replacement_object_returns_empty_mapping_for_empty_df():
    df = pd.DataFrame()

    assert dataframe_to_replacement_object(df, "EMPTY_") == {}
