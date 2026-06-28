import importlib.util
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
VALIDATE_SCRIPT = ROOT / "scripts" / "ci" / "validate_release_branch.py"
VERSION_SCRIPT = ROOT / "scripts" / "ci" / "check_version_consistency.py"
RELEASE_STATE_SCRIPT = ROOT / "scripts" / "ci" / "check_release_artifact_state.py"
LIVE_VALIDATION_SCRIPT = ROOT / "scripts" / "ci" / "check_live_validation_evidence.py"


def _run(
    script: Path, *args: str, cwd: Path = ROOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
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


def _load_script_module(script: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(script.stem, script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _init_release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "tests@example.com")
    _git(repo, "config", "user.name", "Release Tests")

    payload = repo / "payload.txt"
    payload.write_text("first\n")
    _git(repo, "add", "payload.txt")
    _git(repo, "commit", "-qm", "release commit")
    release_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "v1.2.3")

    payload.write_text("second\n")
    _git(repo, "commit", "-am", "follow-up commit")
    follow_up_commit = _git(repo, "rev-parse", "HEAD")

    return repo, release_commit, follow_up_commit


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


def test_version_consistency_collects_changelog_mismatch():
    module = _load_script_module(VERSION_SCRIPT)

    errors = module._collect_version_errors(
        pyproject_version="1.2.3",
        package_version="1.2.3",
        changelog_version="1.2.2",
        release_version=None,
    )

    assert errors == [
        "Changelog latest release mismatch: CHANGELOG.md=1.2.2 vs project=1.2.3"
    ]


def test_release_artifact_state_allows_existing_package_on_tagged_commit(tmp_path):
    repo, release_commit, _ = _init_release_repo(tmp_path)
    output_file = tmp_path / "github-output.txt"

    result = _run(
        RELEASE_STATE_SCRIPT,
        "--version",
        "1.2.3",
        "--expected-commit",
        release_commit,
        "--package-exists-override",
        "true",
        "--release-exists-override",
        "false",
        "--output-file",
        str(output_file),
        cwd=repo,
    )

    output = output_file.read_text()
    assert result.returncode == 0
    assert "Release artifact state validated" in result.stdout
    assert "package_exists=true" in output
    assert "tag_exists=true" in output


def test_release_artifact_state_rejects_existing_package_on_follow_up_commit(tmp_path):
    repo, _, follow_up_commit = _init_release_repo(tmp_path)

    result = _run(
        RELEASE_STATE_SCRIPT,
        "--version",
        "1.2.3",
        "--expected-commit",
        follow_up_commit,
        "--package-exists-override",
        "true",
        "--release-exists-override",
        "false",
        cwd=repo,
    )

    assert result.returncode == 1
    assert "expected artifact-producing commit" in result.stderr


def test_release_artifact_state_rejects_existing_package_without_tag(tmp_path):
    repo, _, follow_up_commit = _init_release_repo(tmp_path)

    result = _run(
        RELEASE_STATE_SCRIPT,
        "--version",
        "9.9.9",
        "--expected-commit",
        follow_up_commit,
        "--package-exists-override",
        "true",
        "--release-exists-override",
        "false",
        cwd=repo,
    )

    assert result.returncode == 1
    assert "matching tag v9.9.9 is missing" in result.stderr


def test_live_validation_accepts_successful_run_for_expected_sha():
    module = _load_script_module(LIVE_VALIDATION_SCRIPT)

    errors = module._validate_run_payload(
        run_name="slides",
        expected_sha="abc123",
        expected_workflow_path=".github/workflows/live-google-slides.yml",
        payload={
            "head_sha": "abc123",
            "status": "completed",
            "conclusion": "success",
            "path": ".github/workflows/live-google-slides.yml",
            "html_url": "https://github.com/example/repo/actions/runs/1",
        },
    )

    assert errors == []


def test_live_validation_rejects_stale_or_failed_run():
    module = _load_script_module(LIVE_VALIDATION_SCRIPT)

    errors = module._validate_run_payload(
        run_name="docs",
        expected_sha="abc123",
        expected_workflow_path=".github/workflows/live-google-docs.yml",
        payload={
            "head_sha": "def456",
            "status": "completed",
            "conclusion": "failure",
            "path": ".github/workflows/live-google-docs.yml",
            "html_url": "https://github.com/example/repo/actions/runs/2",
        },
    )

    assert "docs run SHA mismatch: head_sha='def456' expected='abc123'" in errors
    assert "docs run did not succeed: 'failure'" in errors
