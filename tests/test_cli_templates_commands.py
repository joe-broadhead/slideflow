import pytest

import slideflow.cli.commands.templates as template_commands


class _FakeEngine:
    def __init__(self, names=None, infos=None, raise_on_info=False):
        self._names = names or []
        self._infos = infos or {}
        self._raise_on_info = raise_on_info

    def list_templates(self):
        return list(self._names)

    def get_template_info(self, template_name):
        if self._raise_on_info:
            raise RuntimeError("Template not found")
        return self._infos[template_name]


def test_templates_list_command_prints_names(monkeypatch):
    outputs = []
    engine = _FakeEngine(names=["bar_basic", "combo_bar_line"])

    monkeypatch.setattr(template_commands, "get_template_engine", lambda: engine)
    monkeypatch.setattr(
        template_commands.typer, "echo", lambda msg: outputs.append(msg)
    )

    names = template_commands.templates_list_command(show_details=False)

    assert names == ["bar_basic", "combo_bar_line"]
    assert outputs == ["bar_basic", "combo_bar_line"]


def test_templates_list_command_prints_descriptions_when_requested(monkeypatch):
    outputs = []
    infos = {
        "bar_basic": {
            "name": "Bar Basic",
            "description": "Simple bar chart",
            "version": "1.0",
            "parameters": [],
        }
    }
    engine = _FakeEngine(names=["bar_basic"], infos=infos)

    monkeypatch.setattr(template_commands, "get_template_engine", lambda: engine)
    monkeypatch.setattr(
        template_commands.typer, "echo", lambda msg: outputs.append(msg)
    )

    template_commands.templates_list_command(show_details=True)

    assert outputs == ["bar_basic: Simple bar chart"]


def test_templates_info_command_prints_template_contract(monkeypatch):
    outputs = []
    infos = {
        "bar_basic": {
            "name": "Bar Basic",
            "description": "Simple bar chart",
            "version": "1.0",
            "parameters": [
                {
                    "name": "title",
                    "type": "string",
                    "required": True,
                    "default": None,
                    "description": "Chart title",
                }
            ],
        }
    }
    engine = _FakeEngine(names=["bar_basic"], infos=infos)

    monkeypatch.setattr(template_commands, "get_template_engine", lambda: engine)
    monkeypatch.setattr(
        template_commands.typer, "echo", lambda msg: outputs.append(msg)
    )

    info = template_commands.templates_info_command("bar_basic")

    assert info["name"] == "Bar Basic"
    assert any(line.startswith("name: Bar Basic") for line in outputs)
    assert any("title (string, required)" in line for line in outputs)


def test_templates_info_command_exits_on_missing_template(monkeypatch):
    errors = []
    engine = _FakeEngine(raise_on_info=True)

    monkeypatch.setattr(template_commands, "get_template_engine", lambda: engine)
    monkeypatch.setattr(
        template_commands.typer, "secho", lambda msg, fg=None: errors.append((msg, fg))
    )

    with pytest.raises(template_commands.typer.Exit) as exc_info:
        template_commands.templates_info_command("missing_template")

    assert exc_info.value.code == 1
    assert errors
