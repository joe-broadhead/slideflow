from pathlib import Path

import pytest

from slideflow.builtins.template_engine import TemplateEngine
from slideflow.utilities.exceptions import ChartGenerationError


def test_render_template_supports_block_scalar_template_section(tmp_path):
    template_file = tmp_path / "block_style.yml"
    template_file.write_text(
        "name: Block Template\n"
        "description: Supports template block scalars\n"
        "parameters:\n"
        "  - name: label\n"
        "    type: string\n"
        "    required: true\n"
        "template: |\n"
        "  traces:\n"
        "    - type: \"bar\"\n"
        "      name: \"{{ label }}\"\n"
    )

    engine = TemplateEngine([tmp_path])
    rendered = engine.render_template("block_style", {"label": "Revenue"})

    assert rendered["traces"][0]["type"] == "bar"
    assert rendered["traces"][0]["name"] == "Revenue"


def test_render_template_requires_required_parameters(tmp_path):
    template_file = tmp_path / "required_params.yml"
    template_file.write_text(
        "name: Required Params\n"
        "description: Enforces required config\n"
        "parameters:\n"
        "  - name: metric\n"
        "    type: string\n"
        "    required: true\n"
        "template:\n"
        "  value: \"{{ metric }}\"\n"
    )

    engine = TemplateEngine([tmp_path])

    with pytest.raises(ChartGenerationError, match="Required parameter 'metric' missing"):
        engine.render_template("required_params", {})


def test_list_templates_returns_sorted_template_names(tmp_path):
    (tmp_path / "zeta.yml").write_text(
        "name: Zeta\n"
        "description: z\n"
        "parameters: []\n"
        "template:\n"
        "  v: 1\n"
    )
    (tmp_path / "alpha.yml").write_text(
        "name: Alpha\n"
        "description: a\n"
        "parameters: []\n"
        "template:\n"
        "  v: 1\n"
    )

    engine = TemplateEngine([tmp_path])

    assert engine.list_templates() == ["alpha", "zeta"]
