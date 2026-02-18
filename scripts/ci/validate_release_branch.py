#!/usr/bin/env python3
"""Validate release branch names and extract semantic version.

Expected format: release/vX.Y.Z
"""

from __future__ import annotations

import re
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_release_branch.py <branch-name>", file=sys.stderr)
        return 2

    branch = sys.argv[1]
    match = re.fullmatch(r"release/v(\d+)\.(\d+)\.(\d+)", branch)
    if not match:
        print(
            f"Invalid release branch '{branch}'. Expected format: release/vX.Y.Z",
            file=sys.stderr,
        )
        return 1

    major, minor, patch = match.groups()
    print(f"{major}.{minor}.{patch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
