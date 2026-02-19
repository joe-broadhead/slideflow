import json
import types
from pathlib import Path

import pytest

import slideflow.cli.commands.doctor as doctor_module


def test_doctor_writes_success_json(tmp_path, monkeypatch):
    monkeypatch.setattr(
        doctor_module,
        "_local_environment_checks",
        lambda: [
            {
                "name": "python_version",
                "ok": True,
                "detail": "Python ok",
                "severity": "error",
            }
        ],
    )
    monkeypatch.setattr(
        doctor_module,
        "_provider_checks",
        lambda _config_file, _registry_paths: [
            {
                "name": "provider_init",
                "ok": True,
                "detail": "Provider initialized",
                "severity": "error",
            }
        ],
    )

    config_file = tmp_path / "config.yaml"
    output_file = tmp_path / "doctor.json"
    config_file.write_text(
        "provider: {type: google_slides, config: {}}\n", encoding="utf-8"
    )

    result = doctor_module.doctor_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
        strict=True,
    )

    assert result["status"] == "success"
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["command"] == "doctor"
    assert payload["status"] == "success"


def test_doctor_strict_exits_when_error_checks_fail(monkeypatch):
    monkeypatch.setattr(
        doctor_module,
        "_local_environment_checks",
        lambda: [
            {
                "name": "kaleido_import",
                "ok": False,
                "detail": "kaleido missing",
                "severity": "error",
            }
        ],
    )

    with pytest.raises(doctor_module.typer.Exit) as exc_info:
        doctor_module.doctor_command(
            config_file=None,
            registry_paths=None,
            output_json=None,
            strict=True,
        )

    assert exc_info.value.code == 1


def test_doctor_writes_error_json_when_checks_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(
        doctor_module,
        "_local_environment_checks",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    output_file = tmp_path / "doctor-error.json"
    with pytest.raises(doctor_module.typer.Exit):
        doctor_module.doctor_command(
            config_file=None,
            registry_paths=None,
            output_json=output_file,
            strict=False,
        )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_DOCTOR_FAILED"


def test_doctor_non_strict_does_not_exit_when_provider_checks_fail(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        doctor_module,
        "_local_environment_checks",
        lambda: [
            {
                "name": "python_version",
                "ok": True,
                "detail": "Python ok",
                "severity": "error",
            }
        ],
    )
    monkeypatch.setattr(
        doctor_module,
        "_provider_checks",
        lambda _config_file, _registry_paths: [
            {
                "name": "provider_init",
                "ok": False,
                "detail": "missing credentials",
                "severity": "error",
            }
        ],
    )

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider: {type: google_slides, config: {}}\n", encoding="utf-8"
    )

    result = doctor_module.doctor_command(
        config_file=config_file,
        registry_paths=None,
        output_json=None,
        strict=False,
    )

    assert result["status"] == "error"
    assert result["summary"]["failed_errors"] == 1


def test_detect_chrome_binary_prefers_env_path(monkeypatch, tmp_path):
    chrome_path = tmp_path / "chrome"
    chrome_path.write_text("binary", encoding="utf-8")

    monkeypatch.setenv("CHROME_PATH", str(chrome_path))
    monkeypatch.delenv("GOOGLE_CHROME_BIN", raising=False)
    monkeypatch.setattr(doctor_module.shutil, "which", lambda _name: None)

    assert doctor_module._detect_chrome_binary() == str(chrome_path)


def test_detect_chrome_binary_resolves_env_executable_name(monkeypatch, tmp_path):
    chrome_path = tmp_path / "custom-chrome"
    chrome_path.write_text("binary", encoding="utf-8")

    monkeypatch.setenv("CHROME_PATH", "custom-chrome")
    monkeypatch.delenv("GOOGLE_CHROME_BIN", raising=False)
    monkeypatch.setattr(
        doctor_module.shutil,
        "which",
        lambda name: str(chrome_path) if name == "custom-chrome" else None,
    )

    assert doctor_module._detect_chrome_binary() == str(chrome_path)


def test_local_environment_checks_handles_import_failures(monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name in {"kaleido", "plotly"}:
            raise ImportError(f"{name} missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(doctor_module, "_detect_chrome_binary", lambda: None)
    monkeypatch.delenv(doctor_module.Environment.DATABRICKS_HOST, raising=False)
    monkeypatch.delenv(doctor_module.Environment.DATABRICKS_HTTP_PATH, raising=False)
    monkeypatch.delenv(doctor_module.Environment.DATABRICKS_ACCESS_TOKEN, raising=False)

    checks = doctor_module._local_environment_checks()
    by_name = {check["name"]: check for check in checks}

    assert by_name["kaleido_import"]["ok"] is False
    assert by_name["plotly_import"]["ok"] is False
    assert by_name["chrome_binary"]["ok"] is False
    assert by_name["databricks_env"]["ok"] is False
    assert by_name["databricks_env"]["severity"] == "warning"


def test_local_environment_checks_all_databricks_env_set(monkeypatch):
    monkeypatch.setattr(doctor_module, "_detect_chrome_binary", lambda: "/tmp/chromium")
    monkeypatch.setenv(doctor_module.Environment.DATABRICKS_HOST, "host")
    monkeypatch.setenv(doctor_module.Environment.DATABRICKS_HTTP_PATH, "http_path")
    monkeypatch.setenv(doctor_module.Environment.DATABRICKS_ACCESS_TOKEN, "token")

    checks = doctor_module._local_environment_checks()
    by_name = {check["name"]: check for check in checks}

    assert by_name["chrome_binary"]["ok"] is True
    assert by_name["databricks_env"]["ok"] is True


def test_provider_checks_success(monkeypatch, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("provider: {type: google_slides, config: {}}\n")

    monkeypatch.setattr(
        doctor_module,
        "resolve_registry_paths",
        lambda **_kwargs: [Path("/tmp/registry.py")],
    )
    monkeypatch.setattr(
        doctor_module.yaml, "safe_load", lambda _raw: {"registry": None}
    )
    monkeypatch.setattr(
        doctor_module,
        "ConfigLoader",
        lambda **_kwargs: types.SimpleNamespace(
            config={"provider": {"type": "google"}}
        ),
    )
    monkeypatch.setattr(
        doctor_module,
        "PresentationConfig",
        lambda **_kwargs: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={})
        ),
    )
    monkeypatch.setattr(
        doctor_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        doctor_module.ProviderFactory,
        "create_provider",
        staticmethod(
            lambda _provider_cfg: types.SimpleNamespace(
                run_preflight_checks=lambda: [
                    ("auth", True, "ok"),
                    ("quota", False, "limited"),
                ]
            )
        ),
    )

    checks = doctor_module._provider_checks(config_file, registry_paths=None)
    by_name = {check["name"]: check for check in checks}

    assert by_name["provider_init"]["ok"] is True
    assert by_name["provider:auth"]["ok"] is True
    assert by_name["provider:quota"]["ok"] is False


def test_provider_checks_converts_exceptions_to_failed_check(monkeypatch, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("provider: {type: google_slides, config: {}}\n")
    monkeypatch.setattr(
        doctor_module,
        "ConfigLoader",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("provider boom")),
    )

    checks = doctor_module._provider_checks(config_file, registry_paths=None)

    assert len(checks) == 1
    assert checks[0]["name"] == "provider_init"
    assert checks[0]["ok"] is False
    assert "provider boom" in checks[0]["detail"]


def test_provider_checks_handles_empty_exception_message(monkeypatch, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("provider: {type: google_slides, config: {}}\n")
    monkeypatch.setattr(
        doctor_module,
        "ConfigLoader",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError()),
    )

    checks = doctor_module._provider_checks(config_file, registry_paths=None)

    assert len(checks) == 1
    assert checks[0]["name"] == "provider_init"
    assert checks[0]["ok"] is False
    assert checks[0]["detail"] == "RuntimeError"


def test_doctor_returns_warning_status_when_only_warnings_fail(monkeypatch):
    monkeypatch.setattr(
        doctor_module,
        "_local_environment_checks",
        lambda: [
            {
                "name": "databricks_env",
                "ok": False,
                "detail": "Missing env var",
                "severity": "warning",
            }
        ],
    )

    result = doctor_module.doctor_command(
        config_file=None,
        registry_paths=None,
        output_json=None,
        strict=False,
    )

    assert result["status"] == "warning"
    assert result["summary"]["failed_errors"] == 0
    assert result["summary"]["failed_warnings"] == 1


def test_doctor_error_path_handles_empty_exception_message(tmp_path, monkeypatch):
    monkeypatch.setattr(
        doctor_module,
        "_local_environment_checks",
        lambda: (_ for _ in ()).throw(RuntimeError()),
    )

    output_file = tmp_path / "doctor-error-empty-message.json"
    with pytest.raises(doctor_module.typer.Exit):
        doctor_module.doctor_command(
            config_file=None,
            registry_paths=None,
            output_json=output_file,
            strict=False,
        )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_DOCTOR_FAILED"
    assert payload["error"]["message"] == "RuntimeError"
