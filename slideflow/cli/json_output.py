"""Helpers for writing machine-readable command outputs."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def now_iso8601_utc() -> str:
    """Return current timestamp in ISO 8601 UTC format."""
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_json_value(value: Any) -> Any:
    """Convert values to JSON-safe equivalents."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None

    if isinstance(value, dict):
        return {key: _normalize_json_value(val) for key, val in value.items()}

    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]

    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]

    return value


def write_output_json(path: Optional[Path], payload: Dict[str, Any]) -> None:
    """Write deterministic JSON output when a path is provided."""
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_payload = _normalize_json_value(payload)
    path.write_text(
        json.dumps(
            normalized_payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
