#!/usr/bin/env python3
"""Validate version consistency across project metadata.

Checks:
- pyproject.toml `[project].version`
- slideflow.__version__
- Optional release branch version (release/vX.Y.Z)
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = ROOT / "pyproject.toml"
INIT_PATH = ROOT / "slideflow" / "__init__.py"


def _read_pyproject_version() -> str:
    payload = tomllib.loads(PYPROJECT_PATH.read_text())
    version = payload.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("pyproject.toml is missing [project].version")
    return version


def _read_package_version() -> str:
    match = re.search(
        r"^__version__\s*=\s*['\"]([^'\"]+)['\"]",
        INIT_PATH.read_text(),
        flags = re.MULTILINE,
    )
    if not match:
        raise RuntimeError("slideflow/__init__.py is missing __version__")
    return match.group(1)


def _parse_release_branch_version(branch: str) -> str | None:
    match = re.fullmatch(r"release/v(\d+\.\d+\.\d+)", branch)
    return match.group(1) if match else None


def main() -> int:
    pyproject_version = _read_pyproject_version()
    package_version = _read_package_version()

    if pyproject_version != package_version:
        print(
            "Version mismatch: "
            f"pyproject.toml={pyproject_version} vs slideflow/__init__.py={package_version}",
            file = sys.stderr,
        )
        return 1

    branch = sys.argv[1] if len(sys.argv) > 1 else ""
    release_version = _parse_release_branch_version(branch) if branch else None

    if release_version and release_version != pyproject_version:
        print(
            "Release branch version mismatch: "
            f"branch={release_version} vs project={pyproject_version}",
            file = sys.stderr,
        )
        return 1

    print(f"Version checks passed ({pyproject_version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
