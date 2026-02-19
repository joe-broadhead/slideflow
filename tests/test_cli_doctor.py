import json

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
