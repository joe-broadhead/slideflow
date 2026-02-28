import json
import types
from pathlib import Path

import pytest

import slideflow.cli.commands.build as build_command_module
import slideflow.cli.commands.validate as validate_command_module
import slideflow.presentations.providers.factory as provider_factory_module


def _minimal_loader_config():
    return {
        "provider": {"type": "google_slides", "config": {}},
        "presentation": {"name": "Demo", "slides": []},
    }


def _stub_cli_output(monkeypatch):
    monkeypatch.setattr(
        build_command_module, "print_build_header", lambda *a, **k: None
    )
    monkeypatch.setattr(
        build_command_module, "print_build_progress", lambda *a, **k: None
    )
    monkeypatch.setattr(
        build_command_module, "print_build_success", lambda *a, **k: None
    )
    monkeypatch.setattr(build_command_module, "print_build_error", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module.time, "sleep", lambda *_: None)

    monkeypatch.setattr(
        validate_command_module, "print_validation_header", lambda *a, **k: None
    )
    monkeypatch.setattr(validate_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(
        validate_command_module, "print_config_summary", lambda *a, **k: None
    )
    monkeypatch.setattr(validate_command_module, "print_error", lambda *a, **k: None)


def _stub_presentation_validation(monkeypatch):
    monkeypatch.setattr(
        build_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(slides=[]),
        ),
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(slides=[]),
        ),
    )

    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )


def test_validate_first_error_line_handles_carriage_return_separator():
    error = RuntimeError("first line\rsecond line")
    assert validate_command_module._first_error_line(error) == "first line"


def test_validate_first_error_line_falls_back_to_exception_type_when_empty():
    error = RuntimeError("")
    assert validate_command_module._first_error_line(error) == "RuntimeError"


def test_build_dry_run_validates_all_param_rows_and_uses_empty_registry_default(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)
    _stub_presentation_validation(monkeypatch)

    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    params_path = tmp_path / "params.csv"
    params_path.write_text("region\nus\neu\n")

    loader_calls = []

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths, params):
            loader_calls.append(
                {
                    "yaml_path": yaml_path,
                    "registry_paths": list(registry_paths),
                    "params": params,
                }
            )
            self.config = _minimal_loader_config()

    monkeypatch.setattr(build_command_module, "ConfigLoader", FakeLoader)

    result = build_command_module.build_command(
        config_file=config_file,
        registry_files=None,
        params_path=params_path,
        dry_run=True,
    )

    assert result == []
    assert len(loader_calls) == 2
    assert loader_calls[0]["registry_paths"] == []
    assert loader_calls[1]["registry_paths"] == []
    assert [call["params"]["region"] for call in loader_calls] == ["us", "eu"]


def test_build_fails_when_params_csv_has_no_rows(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path = tmp_path / "params.csv"
    params_path.write_text("region\n")

    with pytest.raises(build_command_module.typer.Exit) as exc_info:
        build_command_module.build_command(
            config_file=config_file,
            registry_files=None,
            params_path=params_path,
            dry_run=True,
        )

    assert exc_info.value.code == 1


def test_build_uses_registry_from_yaml_when_provided(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    _stub_presentation_validation(monkeypatch)

    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "registry: custom_registry.py\n"
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    loader_calls = []

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths, params):
            loader_calls.append(list(registry_paths))
            self.config = _minimal_loader_config()

    monkeypatch.setattr(build_command_module, "ConfigLoader", FakeLoader)

    build_command_module.build_command(
        config_file=config_file,
        registry_files=None,
        params_path=None,
        dry_run=True,
    )

    assert loader_calls == [[(tmp_path / "custom_registry.py").resolve()]]


def test_validate_uses_empty_registry_default_when_registry_file_is_missing(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)
    _stub_presentation_validation(monkeypatch)

    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    loader_calls = []

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            loader_calls.append(list(registry_paths))
            self.config = _minimal_loader_config()

    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)

    validate_command_module.validate_command(
        config_file=config_file, registry_paths=None
    )

    assert loader_calls == [[]]


def test_validate_uses_registry_from_yaml_when_provided(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    _stub_presentation_validation(monkeypatch)

    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "registry: custom_registry.py\n"
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    loader_calls = []

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            loader_calls.append(list(registry_paths))
            self.config = _minimal_loader_config()

    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)

    validate_command_module.validate_command(
        config_file=config_file, registry_paths=None
    )

    assert loader_calls == [[(tmp_path / "custom_registry.py").resolve()]]


def test_validate_calls_deep_slide_validation(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    slide_spec = object()
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    build_calls = []
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda spec: build_calls.append(spec)),
    )

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presentation: {name: Demo, slides: []}\nprovider: {type: google_slides, config: {}}\n"
    )

    validate_command_module.validate_command(
        config_file=config_file, registry_paths=None
    )

    assert build_calls == [slide_spec]


def test_validate_fails_when_deep_slide_validation_fails(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(slides=[object()]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)

    def _raise_slide_validation(_spec):
        raise ValueError("Unresolved function")

    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(_raise_slide_validation),
    )

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presentation: {name: Demo, slides: []}\nprovider: {type: google_slides, config: {}}\n"
    )

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file, registry_paths=None
        )

    assert exc_info.value.code == 1


def test_build_dry_run_fails_when_deep_slide_validation_fails(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    monkeypatch.setattr(
        build_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(slides=[object()]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths, params):
            self.config = _minimal_loader_config()

    monkeypatch.setattr(build_command_module, "ConfigLoader", FakeLoader)

    def _raise_slide_validation(_spec):
        raise ValueError("Unresolved function")

    monkeypatch.setattr(
        build_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(_raise_slide_validation),
    )

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "presentation: {name: Demo, slides: []}\nprovider: {type: google_slides, config: {}}\n"
    )

    with pytest.raises(build_command_module.typer.Exit) as exc_info:
        build_command_module.build_command(
            config_file=config_file,
            registry_files=None,
            params_path=None,
            dry_run=True,
        )

    assert exc_info.value.code == 1


def test_validate_writes_output_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    _stub_presentation_validation(monkeypatch)
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    output_file = tmp_path / "validate.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)

    validate_command_module.validate_command(
        config_file=config_file, registry_paths=None, output_json=output_file
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["command"] == "validate"
    assert payload["status"] == "success"
    assert payload["summary"]["slides"] == 0


def test_build_dry_run_writes_output_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)
    _stub_presentation_validation(monkeypatch)
    monkeypatch.chdir(tmp_path)

    config_file = tmp_path / "config.yaml"
    output_file = tmp_path / "build.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths, params):
            self.config = _minimal_loader_config()

    monkeypatch.setattr(build_command_module, "ConfigLoader", FakeLoader)

    build_command_module.build_command(
        config_file=config_file,
        registry_files=None,
        params_path=None,
        dry_run=True,
        output_json=output_file,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["command"] == "build"
    assert payload["status"] == "success"
    assert payload["dry_run"] is True


def test_build_error_writes_output_json_with_error_code(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "build-error.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("region\n")

    with pytest.raises(build_command_module.typer.Exit):
        build_command_module.build_command(
            config_file=config_file,
            registry_files=None,
            params_path=params_path,
            dry_run=True,
            output_json=output_file,
        )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["command"] == "build"
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_BUILD_FAILED"


def test_validate_provider_contract_check_writes_success_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="slide-contract",
        replacements=[
            types.SimpleNamespace(config={"placeholder": "{{region}}"}),
            types.SimpleNamespace(config={"placeholder": "{{metric}}"}),
        ],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(name="Demo", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakePresentations:
        def __init__(self, payload):
            self._payload = payload
            self.calls = []

        def get(self, presentationId, fields):
            self.calls.append((presentationId, fields))
            return FakeRequest(self._payload[presentationId])

    class FakeProvider:
        def __init__(self, payload):
            self._presentations = FakePresentations(payload)
            self.slides_service = types.SimpleNamespace(
                presentations=lambda: self._presentations
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "template-123"
    provider_payload = {
        template_id: {
            "slides": [
                {
                    "objectId": "slide-contract",
                    "pageElements": [
                        {
                            "shape": {
                                "text": {
                                    "textElements": [
                                        {
                                            "textRun": {
                                                "content": "KPIs {{region}} and {{metric}}"
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    ],
                }
            ]
        }
    }
    fake_provider = FakeProvider(provider_payload)
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: fake_provider),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    validate_command_module.validate_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
        params_path=params_path,
        provider_contract_check=True,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["provider_contract"]["enabled"] is True
    assert payload["provider_contract"]["template_ids"] == [template_id]
    assert payload["provider_contract"]["issues"] == []

    assert fake_provider._presentations.calls == [
        (template_id, validate_command_module._GOOGLE_SLIDES_CONTRACT_FIELDS)
    ]


def test_validate_provider_contract_check_writes_failure_json(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="slide-contract",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(name="Demo", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.slides_service = types.SimpleNamespace(
                presentations=lambda: types.SimpleNamespace(
                    get=lambda presentationId, fields: FakeRequest(
                        payload[presentationId]
                    )
                )
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "template-123"
    provider_payload = {
        template_id: {
            "slides": [
                {
                    "objectId": "other-slide",
                    "pageElements": [],
                }
            ]
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-error.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "SLIDEFLOW_VALIDATE_FAILED"
    assert payload["provider_contract"]["enabled"] is True
    assert payload["provider_contract"]["issues"][0]["type"] == "missing_slide"


def test_validate_provider_contract_check_requires_google_provider(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="mock_provider", config={}),
            presentation=types.SimpleNamespace(name="Demo", slides=[]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: (_ for _ in ()).throw(AssertionError)),
    )

    config_file = tmp_path / "config.yaml"
    output_file = tmp_path / "validate-provider-contract-unsupported.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert (
        "provider types 'google_slides' and 'google_docs'"
        in payload["error"]["message"]
    )


def test_validate_provider_contract_check_merges_duplicate_slide_ids(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    first_slide_spec = types.SimpleNamespace(
        id="slide-contract",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    second_slide_spec = types.SimpleNamespace(
        id="slide-contract",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{metric}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_slides", config={}),
            presentation=types.SimpleNamespace(
                name="Demo", slides=[first_slide_spec, second_slide_spec]
            ),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.slides_service = types.SimpleNamespace(
                presentations=lambda: types.SimpleNamespace(
                    get=lambda presentationId, fields: FakeRequest(
                        payload[presentationId]
                    )
                )
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "template-123"
    provider_payload = {
        template_id: {
            "slides": [
                {
                    "objectId": "slide-contract",
                    "pageElements": [
                        {
                            "shape": {
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "KPI {{metric}} only"}}
                                    ]
                                }
                            }
                        }
                    ],
                }
            ]
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-duplicate-slide-ids.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_slides\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    issue_types = [issue["type"] for issue in payload["provider_contract"]["issues"]]
    assert "missing_placeholder" in issue_types
    assert any(
        issue.get("placeholder") == "{{region}}"
        for issue in payload["provider_contract"]["issues"]
    )


def test_validate_provider_contract_check_google_docs_success(tmp_path, monkeypatch):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeDocuments:
        def __init__(self, payload):
            self._payload = payload
            self.calls = []

        def get(self, documentId):
            self.calls.append(documentId)
            return FakeRequest(self._payload[documentId])

    class FakeProvider:
        def __init__(self, payload):
            self._documents = FakeDocuments(payload)
            self.docs_service = types.SimpleNamespace(documents=lambda: self._documents)
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-1"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "{{SECTION:intro}}Region: {{region}}"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }
    fake_provider = FakeProvider(provider_payload)
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: fake_provider),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-success.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    validate_command_module.validate_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
        params_path=params_path,
        provider_contract_check=True,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["provider_contract"]["provider_type"] == "google_docs"
    assert payload["provider_contract"]["template_ids"] == [template_id]
    assert payload["provider_contract"]["issues"] == []
    assert fake_provider._documents.calls == [template_id]


def test_validate_provider_contract_check_google_docs_ignores_toc_markers(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.docs_service = types.SimpleNamespace(
                documents=lambda: types.SimpleNamespace(
                    get=lambda documentId: FakeRequest(payload[documentId])
                )
            )
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-toc"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "tableOfContents": {
                            "content": [
                                {
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "textRun": {
                                                    "content": "{{SECTION:intro}} TOC"
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "{{SECTION:intro}}Region: {{region}}"
                                    }
                                }
                            ]
                        }
                    },
                ]
            }
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-ignore-toc.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    validate_command_module.validate_command(
        config_file=config_file,
        registry_paths=None,
        output_json=output_file,
        params_path=params_path,
        provider_contract_check=True,
    )

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert payload["provider_contract"]["issues"] == []


def test_validate_provider_contract_check_google_docs_does_not_stitch_split_markers(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.docs_service = types.SimpleNamespace(
                documents=lambda: types.SimpleNamespace(
                    get=lambda documentId: FakeRequest(payload[documentId])
                )
            )
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-split-marker"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "{{SECTION:"}},
                                {"inlineObjectElement": {"inlineObjectId": "kix.1"}},
                                {"textRun": {"content": "intro}} Region: {{region}}"}},
                            ]
                        }
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-split-marker.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    issue_types = [issue["type"] for issue in payload["provider_contract"]["issues"]]
    assert "missing_section_marker" in issue_types


def test_validate_provider_contract_check_google_docs_does_not_stitch_split_placeholders(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.docs_service = types.SimpleNamespace(
                documents=lambda: types.SimpleNamespace(
                    get=lambda documentId: FakeRequest(payload[documentId])
                )
            )
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-split-placeholder"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "{{SECTION:intro}} Value: {{"}},
                                {"inlineObjectElement": {"inlineObjectId": "kix.2"}},
                                {"textRun": {"content": "region}}"}},
                            ]
                        }
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-split-placeholder.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    issue_types = [issue["type"] for issue in payload["provider_contract"]["issues"]]
    assert "missing_placeholder" in issue_types


def test_validate_provider_contract_check_google_docs_missing_section_marker(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.docs_service = types.SimpleNamespace(
                documents=lambda: types.SimpleNamespace(
                    get=lambda documentId: FakeRequest(payload[documentId])
                )
            )
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-2"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "textRun": {
                                        "content": "{{SECTION:summary}}Summary section"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-missing-marker.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    issue_types = [issue["type"] for issue in payload["provider_contract"]["issues"]]
    assert "missing_section_marker" in issue_types


def test_validate_provider_contract_check_google_docs_duplicate_marker(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.docs_service = types.SimpleNamespace(
                documents=lambda: types.SimpleNamespace(
                    get=lambda documentId: FakeRequest(payload[documentId])
                )
            )
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-3"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {
                                    "textRun": {
                                        "content": (
                                            "{{SECTION:intro}}A" "{{SECTION:intro}}B"
                                        )
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-duplicate-marker.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    issue_types = [issue["type"] for issue in payload["provider_contract"]["issues"]]
    assert "duplicate_section_marker" in issue_types


def test_validate_provider_contract_check_google_docs_missing_placeholder(
    tmp_path, monkeypatch
):
    _stub_cli_output(monkeypatch)

    slide_spec = types.SimpleNamespace(
        id="intro",
        replacements=[types.SimpleNamespace(config={"placeholder": "{{region}}"})],
        charts=[],
    )
    monkeypatch.setattr(
        validate_command_module,
        "PresentationConfig",
        lambda **_: types.SimpleNamespace(
            provider=types.SimpleNamespace(type="google_docs", config={}),
            presentation=types.SimpleNamespace(name="Newsletter", slides=[slide_spec]),
        ),
    )
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "get_config_class",
        staticmethod(lambda _provider_type: (lambda **_cfg: None)),
    )
    monkeypatch.setattr(
        validate_command_module.PresentationBuilder,
        "_build_slide",
        staticmethod(lambda _spec: None),
    )

    class FakeLoader:
        def __init__(self, yaml_path: Path, registry_paths):
            self.config = _minimal_loader_config()

    class FakeRequest:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeProvider:
        def __init__(self, payload):
            self.docs_service = types.SimpleNamespace(
                documents=lambda: types.SimpleNamespace(
                    get=lambda documentId: FakeRequest(payload[documentId])
                )
            )
            self.config = types.SimpleNamespace(
                section_marker_prefix="{{SECTION:", section_marker_suffix="}}"
            )

        def _execute_request(self, request):
            return request.execute()

    template_id = "doc-template-4"
    provider_payload = {
        template_id: {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "{{SECTION:intro}}No vars"}}
                            ]
                        }
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(validate_command_module, "ConfigLoader", FakeLoader)
    monkeypatch.setattr(
        provider_factory_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: FakeProvider(provider_payload)),
    )

    config_file = tmp_path / "config.yaml"
    params_path = tmp_path / "params.csv"
    output_file = tmp_path / "validate-provider-contract-docs-missing-placeholder.json"
    config_file.write_text(
        "provider:\n"
        "  type: google_docs\n"
        "  config: {}\n"
        "presentation:\n"
        "  name: Demo\n"
        "  slides: []\n"
    )
    params_path.write_text("template_id\n" f"{template_id}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(
            config_file=config_file,
            registry_paths=None,
            output_json=output_file,
            params_path=params_path,
            provider_contract_check=True,
        )

    assert exc_info.value.code == 1
    payload = json.loads(output_file.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    issue_types = [issue["type"] for issue in payload["provider_contract"]["issues"]]
    assert "missing_placeholder" in issue_types
