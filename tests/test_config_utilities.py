import importlib
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from slideflow.presentations.config import PresentationConfig
from slideflow.utilities.config import (
    ConfigLoader,
    load_registry_from_path,
    render_params,
)
from slideflow.utilities.exceptions import ConfigurationError


def test_load_registry_from_path_returns_registry_and_does_not_leak_sys_path(tmp_path):
    registry_file = tmp_path / "registry.py"
    registry_file.write_text(
        "def fmt(value):\n"
        "    return f'v={value}'\n"
        "\n"
        "function_registry = {'fmt': fmt}\n"
    )

    before = list(sys.path)
    registry = load_registry_from_path(registry_file)
    after = list(sys.path)

    assert "fmt" in registry
    assert callable(registry["fmt"])
    assert registry["fmt"]("x") == "v=x"
    assert before == after


def test_load_registry_from_path_fails_when_file_missing(tmp_path):
    missing = tmp_path / "missing_registry.py"

    with pytest.raises(ConfigurationError, match="Registry file not found"):
        load_registry_from_path(missing)


def test_load_registry_from_path_fails_when_module_spec_is_unavailable(
    tmp_path, monkeypatch
):
    registry_file = tmp_path / "registry.py"
    registry_file.write_text("function_registry = {}\n")

    monkeypatch.setattr(
        importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: None
    )

    with pytest.raises(ConfigurationError, match="Unable to load module specification"):
        load_registry_from_path(registry_file)


def test_load_registry_from_path_forces_target_parent_path_precedence(tmp_path):
    package_name = "shadowpkg"

    bad_parent = tmp_path / "bad_parent"
    good_parent = tmp_path / "good_parent"
    bad_pkg = bad_parent / package_name
    good_pkg = good_parent / package_name
    bad_pkg.mkdir(parents=True)
    good_pkg.mkdir(parents=True)

    (bad_pkg / "__init__.py").write_text("")
    (good_pkg / "__init__.py").write_text("")

    (bad_pkg / "helpers.py").write_text("def source_marker():\n" "    return 'bad'\n")
    (good_pkg / "helpers.py").write_text("def source_marker():\n" "    return 'good'\n")
    registry_file = good_pkg / "registry.py"
    registry_file.write_text(
        "from .helpers import source_marker\n"
        "\n"
        "function_registry = {'source_marker': source_marker}\n"
    )

    package_prefix = f"{package_name}."
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == package_name or name.startswith(package_prefix)
    }
    original_sys_path = list(sys.path)
    sys.path[:] = [str(bad_parent), str(good_parent)] + [
        entry
        for entry in original_sys_path
        if entry not in {str(bad_parent), str(good_parent)}
    ]
    try:
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_prefix):
                sys.modules.pop(name, None)

        bad_helpers = importlib.import_module(f"{package_name}.helpers")
        assert bad_helpers.source_marker() == "bad"

        registry = load_registry_from_path(registry_file)
        assert registry["source_marker"]() == "good"

        restored_helpers = importlib.import_module(f"{package_name}.helpers")
        assert restored_helpers is bad_helpers
        assert restored_helpers.source_marker() == "bad"
    finally:
        sys.path[:] = original_sys_path
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_prefix):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)


def test_render_params_substitutes_single_braces_while_preserving_double_braces():
    payload = {
        "title": "Report {quarter} {{STATIC_TOKEN}}",
        "nested": ["{region}", "{{KEEP_ME}}"],
    }

    rendered = render_params(payload, {"quarter": "Q1", "region": "US"})

    assert rendered["title"] == "Report Q1 {{STATIC_TOKEN}}"
    assert rendered["nested"] == ["US", "{{KEEP_ME}}"]


def test_render_params_tolerates_invalid_format_syntax():
    payload = {
        "broken_left": "prefix {broken",
        "broken_right": "suffix broken}",
        "positional": "value {0}",
    }

    rendered = render_params(payload, {"quarter": "Q1"})

    assert rendered == payload


def test_load_registry_from_path_is_thread_safe_under_concurrency(tmp_path):
    package_name = "threadsafepkg"
    package_parent = tmp_path / "pkg_parent"
    package_dir = package_parent / package_name
    package_dir.mkdir(parents=True)

    (package_dir / "__init__.py").write_text("")
    (package_dir / "helpers.py").write_text(
        "def marker(value):\n"
        "    return f'ok-{value}'\n"
    )
    registry_file = package_dir / "registry.py"
    registry_file.write_text(
        "from .helpers import marker\n"
        "\n"
        "function_registry = {'marker': marker}\n"
    )

    def load_and_call(value: int) -> str:
        registry = load_registry_from_path(registry_file)
        return registry["marker"](value)

    for _round in range(20):
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(load_and_call, range(60)))
        assert results == [f"ok-{value}" for value in range(60)]


def test_config_loader_is_thread_safe_with_shared_registry(tmp_path):
    package_name = "loaderthreadpkg"
    package_parent = tmp_path / "pkg_parent"
    package_dir = package_parent / package_name
    package_dir.mkdir(parents=True)

    (package_dir / "__init__.py").write_text("")
    (package_dir / "helpers.py").write_text(
        "def marker(value):\n"
        "    return f'loader-{value}'\n"
    )
    registry_file = package_dir / "registry.py"
    registry_file.write_text(
        "from .helpers import marker\n"
        "\n"
        "function_registry = {'marker': marker}\n"
    )

    config_file = tmp_path / "config.yml"
    config_file.write_text(
        "rendered: \"{value}\"\n"
        "fn: marker\n"
    )

    def load_config(i: int) -> str:
        loader = ConfigLoader(
            yaml_path=config_file,
            registry_paths=[registry_file],
            params={"value": f"v-{i}"},
        )
        cfg = loader.config
        return f"{cfg['rendered']}|{cfg['fn'](i)}"

    for _round in range(12):
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(load_config, range(40)))
        assert results == [f"v-{i}|loader-{i}" for i in range(40)]


def test_presentation_config_accepts_registry_as_string():
    config = PresentationConfig.model_validate(
        {
            "registry": "registry.py",
            "provider": {"type": "google_slides", "config": {}},
            "presentation": {"name": "Demo", "slides": []},
        }
    )

    assert config.registry == ["registry.py"]
