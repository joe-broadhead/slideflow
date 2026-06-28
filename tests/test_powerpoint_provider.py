from pathlib import Path

import pytest

from slideflow.presentations.base import Presentation, Slide
from slideflow.presentations.config import ProviderConfig
from slideflow.presentations.providers.factory import ProviderFactory
from slideflow.presentations.providers.powerpoint import (
    MEMORY_IMAGE_URL_PREFIX,
    PowerPointProvider,
    PowerPointProviderConfig,
)
from slideflow.utilities.exceptions import ConfigurationError, RenderingError

pptx = pytest.importorskip("pptx")
PIL_Image = pytest.importorskip("PIL.Image")


def _png_bytes(color: str = "red") -> bytes:
    from io import BytesIO

    stream = BytesIO()
    PIL_Image.new("RGB", (32, 24), color).save(stream, format="PNG")
    return stream.getvalue()


def _make_template(path: Path) -> tuple[int, int]:
    prs = pptx.Presentation()
    blank_layout = prs.slide_layouts[6]

    first_slide = prs.slides.add_slide(blank_layout)
    textbox = first_slide.shapes.add_textbox(100000, 100000, 3000000, 500000)
    paragraph = textbox.text_frame.paragraphs[0]
    paragraph.text = ""
    paragraph.add_run().text = "{{NA"
    paragraph.add_run().text = "ME}}"

    table_shape = first_slide.shapes.add_table(1, 1, 100000, 800000, 3000000, 500000)
    table_shape.table.cell(0, 0).text = "Metric: {{METRIC}}"

    second_slide = prs.slides.add_slide(blank_layout)
    second_slide.shapes.add_textbox(100000, 100000, 3000000, 500000).text = (
        "Native {{SECOND}}"
    )
    first_native_id = first_slide.slide_id
    second_native_id = second_slide.slide_id

    prs.save(path)
    return first_native_id, second_native_id


def test_powerpoint_config_rejects_non_pptx_template():
    with pytest.raises(ValueError, match="template_path must point to a .pptx file"):
        PowerPointProviderConfig(template_path="template.ppt")


def test_powerpoint_provider_factory_registration(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)

    provider = ProviderFactory.create_provider(
        ProviderConfig(
            type="powerpoint",
            config={"template_path": template_path, "output_dir": tmp_path},
        )
    )

    assert isinstance(provider, PowerPointProvider)
    assert "powerpoint" in ProviderFactory.get_available_providers()


def test_powerpoint_provider_replaces_text_in_runs_and_table_cells(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
        )
    )
    presentation_id = provider.create_presentation("Deck")

    assert provider.replace_text_in_slide(presentation_id, "1", "{{NAME}}", "Acme") == 1
    assert (
        provider.replace_text_in_slide(presentation_id, "1", "{{METRIC}}", "Revenue")
        == 1
    )

    slide = provider._resolve_slide(presentation_id, "1")
    slide_text = "\n".join(
        paragraph.text
        for text_frame in provider._iter_text_frames(slide.shapes)
        for paragraph in text_frame.paragraphs
    )
    assert "Acme" in slide_text
    assert "Revenue" in slide_text


def test_powerpoint_provider_resolves_native_slide_ids(tmp_path):
    template_path = tmp_path / "template.pptx"
    _first_native_id, second_native_id = _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            slide_id_mode="native",
        )
    )
    presentation_id = provider.create_presentation("Deck")

    assert (
        provider.replace_text_in_slide(
            presentation_id, str(second_native_id), "{{SECOND}}", "Slide"
        )
        == 1
    )
    with pytest.raises(RenderingError, match="was not found"):
        provider.replace_text_in_slide(presentation_id, "2", "{{SECOND}}", "Slide")


def test_powerpoint_provider_inserts_memory_chart_and_saves_pptx(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
            share_with=["team@example.com"],
        )
    )
    presentation_id = provider.create_presentation("Deck")
    image_url, file_id = provider.upload_chart_image(
        presentation_id, _png_bytes(), "chart.png"
    )

    assert image_url.startswith(MEMORY_IMAGE_URL_PREFIX)
    provider.insert_chart_to_slide(presentation_id, "1", image_url, 24, 36, 96, 72)
    provider.delete_chart_image(file_id)
    provider.finalize_presentation(presentation_id)

    output_path = Path(presentation_id)
    assert output_path.is_file()
    rendered = pptx.Presentation(str(output_path))
    assert len(rendered.slides[0].shapes) >= 3
    assert provider.get_presentation_url(presentation_id).startswith("file://")


def test_powerpoint_provider_suffixes_existing_output(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    existing_output = tmp_path / "Deck.pptx"
    existing_output.write_bytes(b"existing")
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
        )
    )

    presentation_id = provider.create_presentation("Deck")

    assert Path(presentation_id).name == "Deck-1.pptx"


def test_powerpoint_provider_fails_on_existing_output_by_default(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    (tmp_path / "Deck.pptx").write_bytes(b"existing")
    provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )

    with pytest.raises(ConfigurationError, match="already exists"):
        provider.create_presentation("Deck")


def test_powerpoint_render_smoke_creates_valid_pptx(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
        )
    )
    presentation = Presentation(
        name="Rendered Deck",
        slides=[
            Slide(
                id="1",
                replacements=[],
                charts=[],
            )
        ],
        provider=provider,
    )

    result = presentation.render()

    assert Path(result.presentation_id).is_file()
    assert result.presentation_url.startswith("file://")
    assert pptx.Presentation(result.presentation_id).slides
