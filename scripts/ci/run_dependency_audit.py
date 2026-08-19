"""Run pip-audit with bounded, expiring dependency exceptions."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    policy_path = root / ".github" / "dependency-audit-exceptions.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(policy, list):
        raise SystemExit("dependency audit exception policy must be a JSON list")

    today = dt.date.today()
    ignored: list[str] = []
    for entry in policy:
        if not isinstance(entry, dict):
            raise SystemExit("dependency audit exception entries must be objects")
        vulnerability = entry.get("vulnerability")
        package = entry.get("package")
        reason = entry.get("reason")
        try:
            expires = dt.date.fromisoformat(entry["expires"])
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit("dependency audit exception has invalid expiry") from error
        if not isinstance(vulnerability, str) or not vulnerability:
            raise SystemExit("dependency audit exception is missing vulnerability")
        if not isinstance(package, str) or not package:
            raise SystemExit("dependency audit exception is missing package")
        if not isinstance(reason, str) or not reason:
            raise SystemExit("dependency audit exception is missing required metadata")
        if today > expires:
            raise SystemExit(
                f"dependency audit exception expired for {package} {vulnerability}"
            )
        ignored.append(vulnerability)

    command = [sys.executable, "-m", "pip_audit", *sys.argv[1:]]
    for vulnerability in ignored:
        command.extend(["--ignore-vuln", vulnerability])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
