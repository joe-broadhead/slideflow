from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pandas as pd

import slideflow.presentations.builder as builder_module
import slideflow.presentations.charts as charts_module
from slideflow.builtins.template_engine import (
    TemplateEngine,
    create_template_engine,
    get_template_engine,
)
from slideflow.presentations.base import Presentation, Slide
from slideflow.presentations.config import PresentationConfig


def _write_named_template(templates_dir, label: str) -> None:
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "shared.yml").write_text(
        "name: Shared Template\n"
        "description: Same template name in isolated directories\n"
        "parameters: []\n"
        "template:\n"
        "  traces:\n"
        '    - type: "bar"\n'
        f'      name: "{label}"\n'
        '      x: "$x"\n'
        '      y: "$y"\n',
        encoding="utf-8",
    )


class _FakePlotlyChart:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        del df
        return str(self.kwargs["traces"][0]["name"]).encode()


def test_template_charts_use_explicit_engine_for_same_template_name(
    tmp_path, monkeypatch
):
    templates_a = tmp_path / "a"
    templates_b = tmp_path / "b"
    _write_named_template(templates_a, "from-a")
    _write_named_template(templates_b, "from-b")
    monkeypatch.setattr(charts_module, "PlotlyGraphObjects", _FakePlotlyChart)

    chart_a = charts_module.TemplateChart(
        template_name="shared",
        template_config={},
        template_engine=TemplateEngine([templates_a]),
    )
    chart_b = charts_module.TemplateChart(
        template_name="shared",
        template_config={},
        template_engine=TemplateEngine([templates_b]),
    )

    frame = pd.DataFrame({"x": ["one"], "y": [1]})

    assert chart_a.generate_chart_image(frame) == b"from-a"
    assert chart_b.generate_chart_image(frame) == b"from-b"


def test_concurrent_builds_keep_template_paths_isolated(tmp_path, monkeypatch):
    templates_a = tmp_path / "a"
    templates_b = tmp_path / "b"
    _write_named_template(templates_a, "from-a")
    _write_named_template(templates_b, "from-b")

    barrier = threading.Barrier(2)

    class _ConcurrentFakePlotlyChart(_FakePlotlyChart):
        def generate_chart_image(self, df: pd.DataFrame) -> bytes:
            barrier.wait(timeout=5)
            return super().generate_chart_image(df)

    monkeypatch.setattr(
        builder_module.ProviderFactory,
        "create_provider",
        staticmethod(lambda _provider_config: object()),
    )
    monkeypatch.setattr(
        builder_module,
        "Presentation",
        SimpleNamespace,
    )
    monkeypatch.setattr(charts_module, "PlotlyGraphObjects", _ConcurrentFakePlotlyChart)

    def _config(template_path) -> PresentationConfig:
        return PresentationConfig.model_validate(
            {
                "template_paths": [str(template_path)],
                "provider": {"type": "google_slides", "config": {}},
                "presentation": {
                    "name": "Demo",
                    "slides": [
                        {
                            "id": "slide_1",
                            "charts": [
                                {
                                    "type": "template",
                                    "config": {
                                        "template_name": "shared",
                                        "template_config": {},
                                    },
                                }
                            ],
                        }
                    ],
                },
            }
        )

    def _render(config: PresentationConfig) -> bytes:
        presentation = builder_module.PresentationBuilder.from_config(config)
        chart = presentation.slides[0].charts[0]
        return chart.generate_chart_image(pd.DataFrame({"x": ["one"], "y": [1]}))

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(_render, _config(templates_a))
        future_b = executor.submit(_render, _config(templates_b))

    assert future_a.result(timeout=5) == b"from-a"
    assert future_b.result(timeout=5) == b"from-b"


def test_custom_chart_get_template_engine_uses_build_scoped_engine(tmp_path):
    templates_dir = tmp_path / "custom"
    _write_named_template(templates_dir, "from-custom")

    def _chart_fn(df: pd.DataFrame, config: dict[str, Any], chart) -> bytes:
        del df, config, chart
        rendered = get_template_engine().render_template("shared", {})
        return str(rendered["traces"][0]["name"]).encode()

    chart = builder_module.PresentationBuilder._build_chart(
        SimpleNamespace(
            type="custom",
            config={
                "chart_fn": _chart_fn,
                "chart_config": {},
            },
        ),
        template_engine=create_template_engine([templates_dir]),
    )

    class _Provider:
        def __init__(self) -> None:
            self.uploaded: bytes | None = None

        def upload_chart_image(
            self, presentation_id: str, image_data: bytes, filename: str
        ):
            del presentation_id, filename
            self.uploaded = image_data
            return ("https://example.com/chart.png", "file-1")

        def insert_chart_to_slide(self, *_args: Any) -> None:
            pass

    provider = _Provider()
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[],
        provider=provider,
    )
    context = SimpleNamespace(
        presentation_id="presentation-1",
        uploaded_file_ids=[],
        content_errors=[],
        total_charts=0,
        allow_partial_render=False,
        slides_app=Presentation._to_slides_app_dimensions(720, 540),
        page_width_pt=720,
        page_height_pt=540,
    )
    slide = Slide.model_construct(
        id="slide_1", title="Slide", replacements=[], charts=[]
    )

    presentation._process_single_chart(context, slide, chart)

    assert provider.uploaded == b"from-custom"
