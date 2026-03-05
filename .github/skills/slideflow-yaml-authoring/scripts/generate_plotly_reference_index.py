#!/usr/bin/env python3
"""Generate a Plotly trace/layout property index for skill references.

Usage:
  python .github/skills/slideflow-yaml-authoring/scripts/generate_plotly_reference_index.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRACE_CLASS_MAP = {
    "bar": "Bar",
    "scatter": "Scatter",
    "pie": "Pie",
    "funnel": "Funnel",
    "indicator": "Indicator",
    "table": "Table",
    "heatmap": "Heatmap",
    "histogram": "Histogram",
    "box": "Box",
    "waterfall": "Waterfall",
}


def _sorted_props(plotly_obj: Any) -> list[str]:
    """Return sorted property names for a Plotly graph object."""
    valid_props = getattr(plotly_obj, "_valid_props", None)
    if valid_props:
        return sorted(str(prop) for prop in valid_props)

    fallback = plotly_obj.to_plotly_json()
    return sorted(str(key) for key in fallback.keys())


def _collect_reference(*, no_timestamp: bool = False) -> dict[str, Any]:
    try:
        import plotly
        import plotly.graph_objects as go
    except ImportError as exc:
        raise RuntimeError(
            "Plotly is required. Install with: python -m pip install plotly"
        ) from exc

    traces: dict[str, list[str]] = {}
    for trace_key, class_name in TRACE_CLASS_MAP.items():
        trace_cls = getattr(go, class_name, None)
        if trace_cls is None:
            continue
        trace_props = _sorted_props(trace_cls())
        if trace_props:
            traces[trace_key] = trace_props

    layout_props = _sorted_props(go.Layout())
    if not traces:
        raise RuntimeError("No trace properties collected from Plotly.")
    if not layout_props:
        raise RuntimeError("No layout properties collected from Plotly.")

    metadata: dict[str, Any] = {
        "plotly_version": plotly.__version__,
        "trace_count": len(traces),
        "layout_property_count": len(layout_props),
    }
    if not no_timestamp:
        metadata["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    return {"metadata": metadata, "traces": traces, "layout": layout_props}


def _default_output_path() -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    return skill_root / "references" / "plotly-reference-index.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate plotly-reference-index.json for slideflow skill docs."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output_path(),
        help="Output JSON path (default: skill references directory).",
    )
    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Omit generated_at_utc from metadata for deterministic output.",
    )
    args = parser.parse_args()

    payload = _collect_reference(no_timestamp=args.no_timestamp)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"Wrote {args.output}")
    print(
        "Collected "
        f"{payload['metadata']['trace_count']} traces and "
        f"{payload['metadata']['layout_property_count']} layout properties "
        f"(plotly {payload['metadata']['plotly_version']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
