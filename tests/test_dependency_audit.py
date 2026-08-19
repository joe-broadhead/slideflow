import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = ROOT / "scripts" / "ci" / "run_dependency_audit.py"


def _load_audit_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "slideflow_dependency_audit", AUDIT_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_policy(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        ["not-an-object"],
        [{"package": "sqlparse", "vulnerability": "CVE-1", "expires": "2027-01-01"}],
        [
            {
                "package": "sqlparse",
                "vulnerability": "CVE-1",
                "reason": "temporary exception",
                "expires": "not-a-date",
            }
        ],
    ],
)
def test_dependency_audit_rejects_malformed_policy(tmp_path, payload):
    module = _load_audit_module()
    policy_path = tmp_path / "policy.json"
    _write_policy(policy_path, payload)

    with pytest.raises(SystemExit, match="dependency audit exception"):
        module._load_policy(policy_path, today=dt.date(2026, 8, 19))


def test_dependency_audit_rejects_expired_policy(tmp_path):
    module = _load_audit_module()
    policy_path = tmp_path / "policy.json"
    _write_policy(
        policy_path,
        [
            {
                "package": "sqlparse",
                "vulnerability": "CVE-1",
                "reason": "temporary exception",
                "expires": "2026-08-18",
            }
        ],
    )

    with pytest.raises(SystemExit, match="expired for sqlparse CVE-1"):
        module._load_policy(policy_path, today=dt.date(2026, 8, 19))


def test_dependency_audit_scopes_suppression_to_package_and_keeps_findings_visible(
    tmp_path, monkeypatch
):
    module = _load_audit_module()
    policy_path = tmp_path / "policy.json"
    output_path = tmp_path / "audit.json"
    _write_policy(
        policy_path,
        [
            {
                "package": "SQLParse",
                "vulnerability": "CVE-1",
                "reason": "blocked by dbt-core",
                "expires": "2026-11-18",
            }
        ],
    )
    raw_audit = {
        "dependencies": [
            {
                "name": "sqlparse",
                "version": "0.5.4",
                "vulns": [
                    {
                        "id": "PYSEC-1",
                        "aliases": ["CVE-1"],
                        "fix_versions": ["0.6.0"],
                    }
                ],
            },
            {
                "name": "unrelated-package",
                "version": "1.0",
                "vulns": [
                    {
                        "id": "CVE-1",
                        "aliases": [],
                        "fix_versions": ["2.0"],
                    }
                ],
            },
        ],
        "fixes": [],
    }
    captured_command = []

    def _fake_run(command, check):
        assert check is False
        captured_command.extend(command)
        raw_output = Path(command[command.index("--output") + 1])
        raw_output.write_text(json.dumps(raw_audit), encoding="utf-8")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    returncode = module.main(
        ["--format=json", "--output", str(output_path), "--progress-spinner", "off"],
        policy_path=policy_path,
        today=dt.date(2026, 8, 19),
    )

    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    suppressed = artifact["dependencies"][0]["vulns"][0]
    active = artifact["dependencies"][1]["vulns"][0]
    assert returncode == 1
    assert "--ignore-vuln" not in captured_command
    assert suppressed["status"] == "suppressed"
    assert suppressed["suppression"] == {
        "package": "SQLParse",
        "vulnerability": "CVE-1",
        "reason": "blocked by dbt-core",
        "expires": "2026-11-18",
    }
    assert active["status"] == "active"
    assert "suppression" not in active
    assert artifact["summary"] == {
        "active_vulnerabilities": 1,
        "suppressed_vulnerabilities": 1,
    }


def test_dependency_audit_succeeds_when_every_finding_is_suppressed(
    tmp_path, monkeypatch
):
    module = _load_audit_module()
    policy_path = tmp_path / "policy.json"
    _write_policy(
        policy_path,
        [
            {
                "package": "sqlparse",
                "vulnerability": "CVE-1",
                "reason": "blocked by dbt-core",
                "expires": "2026-11-18",
            }
        ],
    )

    def _fake_run(command, check):
        assert check is False
        raw_output = Path(command[command.index("--output") + 1])
        raw_output.write_text(
            json.dumps(
                {
                    "dependencies": [
                        {
                            "name": "sqlparse",
                            "version": "0.5.4",
                            "vulns": [
                                {"id": "CVE-1", "aliases": [], "fix_versions": []}
                            ],
                        }
                    ],
                    "fixes": [],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    returncode = module.main(
        ["--progress-spinner", "off"],
        policy_path=policy_path,
        today=dt.date(2026, 8, 19),
    )

    assert returncode == 0


def test_dependency_audit_propagates_operational_failure_without_output(
    tmp_path, monkeypatch
):
    module = _load_audit_module()
    policy_path = tmp_path / "policy.json"
    _write_policy(policy_path, [])
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda _command, check: SimpleNamespace(returncode=2),
    )

    returncode = module.main([], policy_path=policy_path, today=dt.date(2026, 8, 19))

    assert returncode == 2


def test_dependency_audit_rejects_invalid_audit_json(tmp_path, monkeypatch):
    module = _load_audit_module()
    policy_path = tmp_path / "policy.json"
    _write_policy(policy_path, [])

    def _fake_run(command, check):
        assert check is False
        raw_output = Path(command[command.index("--output") + 1])
        raw_output.write_text("not-json", encoding="utf-8")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    with pytest.raises(SystemExit, match="pip-audit produced invalid JSON"):
        module.main([], policy_path=policy_path, today=dt.date(2026, 8, 19))
