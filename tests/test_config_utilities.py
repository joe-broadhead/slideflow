import importlib.util
import sys
from pathlib import Path

import pytest

from slideflow.utilities.config import load_registry_from_path
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


def test_load_registry_from_path_fails_when_module_spec_is_unavailable(tmp_path, monkeypatch):
    registry_file = tmp_path / "registry.py"
    registry_file.write_text("function_registry = {}\n")

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: None)

    with pytest.raises(ConfigurationError, match="Unable to load module specification"):
        load_registry_from_path(registry_file)
