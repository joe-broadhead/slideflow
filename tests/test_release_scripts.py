import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = ROOT / "scripts" / "ci" / "validate_release_branch.py"
VERSION_SCRIPT = ROOT / "scripts" / "ci" / "check_version_consistency.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _current_version() -> str:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return str(payload["project"]["version"])


def _mismatched_release_branch() -> str:
    major, minor, patch = _current_version().split(".")
    return f"release/v{major}.{minor}.{int(patch) + 1}"


def test_validate_release_branch_accepts_semver_release_branch():
    version = _current_version()
    result = _run(VALIDATE_SCRIPT, f"release/v{version}")

    assert result.returncode == 0
    assert result.stdout.strip() == version


def test_validate_release_branch_rejects_invalid_branch_format():
    result = _run(VALIDATE_SCRIPT, "release/0.0.2")

    assert result.returncode == 1
    assert "Invalid release branch" in result.stderr


def test_check_version_consistency_passes_for_current_metadata():
    version = _current_version()
    result = _run(VERSION_SCRIPT)

    assert result.returncode == 0
    assert f"Version checks passed ({version})" in result.stdout


def test_check_version_consistency_fails_for_mismatched_release_branch_version():
    result = _run(VERSION_SCRIPT, _mismatched_release_branch())

    assert result.returncode == 1
    assert "Release branch version mismatch" in result.stderr
