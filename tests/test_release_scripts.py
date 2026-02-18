import subprocess
import sys
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


def test_validate_release_branch_accepts_semver_release_branch():
    result = _run(VALIDATE_SCRIPT, "release/v0.0.2")

    assert result.returncode == 0
    assert result.stdout.strip() == "0.0.2"


def test_validate_release_branch_rejects_invalid_branch_format():
    result = _run(VALIDATE_SCRIPT, "release/0.0.2")

    assert result.returncode == 1
    assert "Invalid release branch" in result.stderr


def test_check_version_consistency_passes_for_current_metadata():
    result = _run(VERSION_SCRIPT)

    assert result.returncode == 0
    assert "Version checks passed (0.0.2)" in result.stdout


def test_check_version_consistency_fails_for_mismatched_release_branch_version():
    result = _run(VERSION_SCRIPT, "release/v0.0.3")

    assert result.returncode == 1
    assert "Release branch version mismatch" in result.stderr
