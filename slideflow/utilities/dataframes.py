"""DataFrame utility helpers shared across runtime components."""

import pandas as pd


def copy_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return an isolated copy of a pandas-compatible DataFrame."""
    copy_method = getattr(df, "copy", None)
    if callable(copy_method):
        try:
            return copy_method(deep=True)
        except TypeError:
            return copy_method()
    return pd.DataFrame(df)
