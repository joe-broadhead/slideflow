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
    monkeypatch.setattr(build_command_module, "print_build_header", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module, "print_build_progress", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module, "print_build_success", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module, "print_build_error", lambda *a, **k: None)
    monkeypatch.setattr(build_command_module.time, "sleep", lambda *_: None)

    monkeypatch.setattr(validate_command_module, "print_validation_header", lambda *a, **k: None)
    monkeypatch.setattr(validate_command_module, "print_success", lambda *a, **k: None)
    monkeypatch.setattr(validate_command_module, "print_config_summary", lambda *a, **k: None)
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


def test_build_dry_run_validates_all_param_rows_and_uses_empty_registry_default(tmp_path, monkeypatch):
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

    assert loader_calls == [[Path("custom_registry.py")]]


def test_validate_uses_empty_registry_default_when_registry_file_is_missing(tmp_path, monkeypatch):
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

    validate_command_module.validate_command(config_file=config_file, registry_paths=None)

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

    validate_command_module.validate_command(config_file=config_file, registry_paths=None)

    assert loader_calls == [[Path("custom_registry.py")]]


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
    config_file.write_text("presentation: {name: Demo, slides: []}\nprovider: {type: google_slides, config: {}}\n")

    validate_command_module.validate_command(config_file=config_file, registry_paths=None)

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
    config_file.write_text("presentation: {name: Demo, slides: []}\nprovider: {type: google_slides, config: {}}\n")

    with pytest.raises(validate_command_module.typer.Exit) as exc_info:
        validate_command_module.validate_command(config_file=config_file, registry_paths=None)

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
    config_file.write_text("presentation: {name: Demo, slides: []}\nprovider: {type: google_slides, config: {}}\n")

    with pytest.raises(build_command_module.typer.Exit) as exc_info:
        build_command_module.build_command(
            config_file=config_file,
            registry_files=None,
            params_path=None,
            dry_run=True,
        )

    assert exc_info.value.code == 1
