"""Helpers for writing machine-readable command outputs."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def now_iso8601_utc() -> str:
    """Return current timestamp in ISO 8601 UTC format."""
    return datetime.now(tz=timezone.utc).isoformat()


def write_output_json(path: Optional[Path], payload: Dict[str, Any]) -> None:
    """Write deterministic JSON output when a path is provided."""
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
