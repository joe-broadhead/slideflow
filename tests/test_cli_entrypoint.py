import runpy
import sys
import types
from pathlib import Path

import pytest


def _run_cli_entrypoint(monkeypatch, app_fn):
    fake_main_module = types.ModuleType("slideflow.cli.main")
    fake_main_module.app = app_fn
    monkeypatch.setitem(sys.modules, "slideflow.cli.main", fake_main_module)
    module_path = Path(__file__).resolve().parents[1] / "slideflow" / "cli.py"
    runpy.run_path(str(module_path), run_name="__main__")


def test_cli_entrypoint_swallows_zero_system_exit(monkeypatch):
    def app():
        raise SystemExit(0)

    _run_cli_entrypoint(monkeypatch, app)


def test_cli_entrypoint_reraises_non_zero_system_exit(monkeypatch):
    def app():
        raise SystemExit(2)

    with pytest.raises(SystemExit) as exc_info:
        _run_cli_entrypoint(monkeypatch, app)

    assert exc_info.value.code == 2
