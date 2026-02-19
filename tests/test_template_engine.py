from pathlib import Path

import pytest

import slideflow.builtins.template_engine as template_engine_module
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
        '    - type: "bar"\n'
        '      name: "{{ label }}"\n'
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
        '  value: "{{ metric }}"\n'
    )

    engine = TemplateEngine([tmp_path])

    with pytest.raises(
        ChartGenerationError, match="Required parameter 'metric' missing"
    ):
        engine.render_template("required_params", {})


def test_list_templates_returns_sorted_template_names(tmp_path):
    (tmp_path / "zeta.yml").write_text(
        "name: Zeta\n" "description: z\n" "parameters: []\n" "template:\n" "  v: 1\n"
    )
    (tmp_path / "alpha.yml").write_text(
        "name: Alpha\n" "description: a\n" "parameters: []\n" "template:\n" "  v: 1\n"
    )

    engine = TemplateEngine([tmp_path])

    assert engine.list_templates() == ["alpha", "zeta"]


def test_default_engine_can_load_packaged_builtin_templates():
    engine = TemplateEngine()
    rendered = engine.render_template(
        "bar_basic",
        {"title": "Revenue", "x_column": "month", "y_column": "revenue"},
    )

    assert rendered["traces"][0]["type"] == "bar"
    assert rendered["layout_config"]["title"] == "Revenue"


def test_local_template_precedence_overrides_packaged_builtin(tmp_path):
    custom_templates = tmp_path / "templates"
    custom_templates.mkdir(parents=True, exist_ok=True)
    (custom_templates / "bar_basic.yml").write_text(
        "name: Local Override\n"
        "description: Local override for built-in bar_basic\n"
        "parameters:\n"
        "  - name: title\n"
        "    type: string\n"
        "    required: true\n"
        "template:\n"
        "  traces:\n"
        '    - type: "scatter"\n'
        "  layout_config:\n"
        '    title: "{{ title }}"\n'
    )

    builtins_path = (
        Path(template_engine_module.__file__).resolve().parents[1] / "templates"
    )
    engine = TemplateEngine([custom_templates, builtins_path])
    template = engine.load_template("bar_basic")

    assert template.name == "Local Override"


def test_kpi_single_template_renders_scalar_column_reference_by_default():
    engine = TemplateEngine()

    rendered = engine.render_template(
        "kpi_cards/kpi_card_single",
        {"title": "ARR", "value_column": "arr"},
    )

    assert rendered["traces"][0]["type"] == "indicator"
    assert rendered["traces"][0]["value"] == "$arr[0]"


def test_kpi_delta_template_renders_scalar_column_references_by_default():
    engine = TemplateEngine()

    rendered = engine.render_template(
        "kpi_cards/kpi_card_delta",
        {"title": "ARR", "value_column": "arr", "reference_column": "arr_prev"},
    )

    assert rendered["traces"][0]["type"] == "indicator"
    assert rendered["traces"][0]["value"] == "$arr[0]"
    assert rendered["traces"][0]["delta"]["reference"] == "$arr_prev[0]"


def test_waterfall_delta_template_does_not_set_invalid_scalar_measure():
    engine = TemplateEngine()

    rendered = engine.render_template(
        "composition/waterfall_delta",
        {
            "title": "Contributions",
            "label_column": "segment",
            "value_column": "delta_value",
        },
    )

    trace = rendered["traces"][0]
    assert trace["type"] == "waterfall"
    assert trace["x"] == "$segment"
    assert trace["y"] == "$delta_value"
    assert "measure" not in trace
