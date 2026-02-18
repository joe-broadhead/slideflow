#!/usr/bin/env python3
"""Generate a lightweight Plotly trace/layout property reference index.

Usage:
  python skills/slideflow-yaml-authoring/scripts/generate_plotly_reference_index.py
"""

from __future__ import annotations

import json
from pathlib import Path


def _collect_reference() -> dict[str, object]:
    import plotly.graph_objects as go

    trace_types = [
        "Bar",
        "Scatter",
        "Pie",
        "Funnel",
        "Indicator",
        "Table",
        "Heatmap",
        "Histogram",
        "Box",
        "Waterfall",
    ]

    traces: dict[str, list[str]] = {}
    for trace_name in trace_types:
        trace_cls = getattr(go, trace_name)
        trace_obj = trace_cls()
        traces[trace_name.lower()] = sorted(trace_obj.to_plotly_json().keys())

    layout = go.Layout()
    layout_keys = sorted(layout.to_plotly_json().keys())

    return {
        "traces": traces,
        "layout": layout_keys,
    }


def main() -> int:
    output_path = (
        Path(__file__).resolve().parents[1]
        / "references"
        / "plotly-reference-index.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = _collect_reference()
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
