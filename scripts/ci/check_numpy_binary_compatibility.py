#!/usr/bin/env python3
"""Fail CI when NumPy/Pandas ABI mismatch warnings are detected.

This catches warnings like:
  "numpy.integer size changed, may indicate binary incompatibility"
"""

from __future__ import annotations

import warnings

ABI_WARNING_FRAGMENT = "size changed, may indicate binary incompatibility"


def _format_warning(warning_item: warnings.WarningMessage) -> str:
    filename = warning_item.filename or "<unknown>"
    lineno = warning_item.lineno or 0
    message = str(warning_item.message)
    return f"{filename}:{lineno}: {warning_item.category.__name__}: {message}"


def main() -> int:
    caught: list[warnings.WarningMessage]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        import numpy as np
        import pandas as pd

        # Touch C-extension-backed paths after import so ABI warnings surface
        # during this check rather than later in runtime.
        frame = pd.DataFrame({"value": [1, 2, 3]})
        _ = frame["value"].to_numpy()
        _ = np.asarray([1, 2, 3], dtype=np.int64)

    abi_warnings = [
        warning_item
        for warning_item in caught
        if issubclass(warning_item.category, RuntimeWarning)
        and ABI_WARNING_FRAGMENT in str(warning_item.message)
    ]

    if abi_warnings:
        print("NumPy/Pandas ABI mismatch warning(s) detected:")
        for warning_item in abi_warnings:
            print(f"- {_format_warning(warning_item)}")
        print("")
        print("Recommended fix:")
        print("  python -m venv .venv")
        print("  source .venv/bin/activate")
        print("  python -m pip install --upgrade pip")
        print('  python -m pip install -e ".[dev,ai,docs]"')
        return 1

    print("NumPy/Pandas ABI check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
