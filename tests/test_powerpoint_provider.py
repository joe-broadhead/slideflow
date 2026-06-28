import stat
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


def test_powerpoint_config_rejects_unresolved_template_path_param():
    with pytest.raises(ValueError, match="template_path must point to a .pptx file"):
        PowerPointProviderConfig(template_path="{template_path}")


@pytest.mark.parametrize(
    "template_path",
    ["{template_dir}/report.pdf", "templates/{quarter}.ppt"],
)
def test_powerpoint_config_rejects_parameterized_static_non_pptx_suffix(template_path):
    with pytest.raises(ValueError, match="template_path must point to a .pptx file"):
        PowerPointProviderConfig(template_path=template_path)


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


def test_powerpoint_provider_preflight_accepts_creatable_nested_output_dir(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path / "missing" / "nested",
        )
    )

    checks = dict((name, ok) for name, ok, _detail in provider.run_preflight_checks())

    assert checks["output_dir_writable"] is True


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


def test_powerpoint_provider_does_not_reprocess_replacement_placeholder_text(
    tmp_path,
):
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

    replacements = provider.replace_text_in_slide(
        presentation_id, "2", "{{SECOND}}", "{{SECOND}} Inc"
    )

    slide = provider._resolve_slide(presentation_id, "2")
    slide_text = "\n".join(
        paragraph.text
        for text_frame in provider._iter_text_frames(slide.shapes)
        for paragraph in text_frame.paragraphs
    )
    assert replacements == 1
    assert "{{SECOND}} Inc" in slide_text
    assert "{{SECOND}} Inc Inc" not in slide_text


def test_powerpoint_provider_replaces_mixed_run_and_split_placeholders(tmp_path):
    template_path = tmp_path / "template.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    textbox = slide.shapes.add_textbox(100000, 100000, 3000000, 500000)
    paragraph = textbox.text_frame.paragraphs[0]
    paragraph.text = ""
    paragraph.add_run().text = "{{NAME}} and {{NA"
    paragraph.add_run().text = "ME}}"
    prs.save(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
        )
    )
    presentation_id = provider.create_presentation("Deck")

    replacements = provider.replace_text_in_slide(
        presentation_id, "1", "{{NAME}}", "Acme"
    )

    slide = provider._resolve_slide(presentation_id, "1")
    slide_text = "\n".join(
        paragraph.text
        for text_frame in provider._iter_text_frames(slide.shapes)
        for paragraph in text_frame.paragraphs
    )
    assert replacements == 2
    assert "Acme and Acme" in slide_text


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


def test_powerpoint_provider_reserves_suffix_paths_before_finalize(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    first_provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
        )
    )
    second_provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="suffix",
        )
    )

    first_id = first_provider.create_presentation("Deck")
    second_id = second_provider.create_presentation("Deck")

    assert Path(first_id).name == "Deck.pptx"
    assert Path(second_id).name == "Deck-1.pptx"
    assert not Path(first_id).exists()
    assert not Path(second_id).exists()

    first_provider.finalize_presentation(first_id)
    second_provider.finalize_presentation(second_id)

    assert Path(first_id).is_file()
    assert Path(second_id).is_file()


def test_powerpoint_provider_uses_bounded_auxiliary_paths_for_long_names(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )
    long_name = "A" * 220

    presentation_id = provider.create_presentation(long_name)
    lock_files = list(tmp_path.glob(".*.lock"))

    assert len(lock_files) == 1
    assert len(lock_files[0].name.encode("utf-8")) < 255

    provider.finalize_presentation(presentation_id)

    assert len(Path(presentation_id).name.encode("utf-8")) < 255
    assert Path(presentation_id).is_file()
    assert not lock_files[0].exists()


def test_powerpoint_provider_fail_strategy_reserves_path_before_finalize(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    first_provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )
    second_provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )

    first_provider.create_presentation("Deck")

    with pytest.raises(ConfigurationError, match="already exists"):
        second_provider.create_presentation("Deck")


def test_powerpoint_provider_releases_reserved_path_on_abort(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    first_provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )
    second_provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )

    first_id = first_provider.create_presentation("Deck")

    assert not Path(first_id).exists()
    with pytest.raises(ConfigurationError, match="already exists"):
        second_provider.create_presentation("Deck")

    first_provider.abort_presentation(first_id)
    second_id = second_provider.create_presentation("Deck")

    assert Path(second_id) == tmp_path / "Deck.pptx"


def test_powerpoint_provider_releases_reserved_path_on_template_load_interrupt(
    tmp_path,
):
    class TemplateLoadInterrupted(BaseException):
        pass

    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )

    def interrupt_template_load(_template_path):
        raise TemplateLoadInterrupted()

    provider._pptx_factory = interrupt_template_load

    with pytest.raises(TemplateLoadInterrupted):
        provider.create_presentation("Deck")

    retry_provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )
    retry_id = retry_provider.create_presentation("Deck")

    assert Path(retry_id) == tmp_path / "Deck.pptx"


def test_powerpoint_provider_fails_on_existing_output_by_default(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    (tmp_path / "Deck.pptx").write_bytes(b"existing")
    provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )

    with pytest.raises(ConfigurationError, match="already exists"):
        provider.create_presentation("Deck")


def test_powerpoint_provider_overwrite_preserves_existing_file_until_finalize(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    output_path = tmp_path / "Deck.pptx"
    original_bytes = b"existing deck bytes"
    output_path.write_bytes(original_bytes)
    output_path.chmod(0o600)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="overwrite",
        )
    )

    presentation_id = provider.create_presentation("Deck")

    assert Path(presentation_id) == output_path
    assert output_path.read_bytes() == original_bytes

    provider.finalize_presentation(presentation_id)

    assert output_path.read_bytes() != original_bytes
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
    assert pptx.Presentation(str(output_path)).slides


def test_powerpoint_provider_applies_existing_mode_before_temp_save(tmp_path):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    output_path = tmp_path / "Deck.pptx"
    output_path.write_bytes(b"existing deck bytes")
    output_path.chmod(0o600)
    provider = PowerPointProvider(
        PowerPointProviderConfig(
            template_path=template_path,
            output_dir=tmp_path,
            file_collision_strategy="overwrite",
        )
    )
    presentation_id = provider.create_presentation("Deck")
    observed_modes = []

    class FakePresentation:
        @staticmethod
        def save(path: str) -> None:
            temp_path = Path(path)
            observed_modes.append(stat.S_IMODE(temp_path.stat().st_mode))
            temp_path.write_bytes(b"updated deck bytes")

    provider._presentations[presentation_id] = FakePresentation()

    provider.finalize_presentation(presentation_id)

    assert observed_modes == [0o600]
    assert output_path.read_bytes() == b"updated deck bytes"
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600


def test_powerpoint_render_failure_releases_output_reservation(tmp_path, monkeypatch):
    template_path = tmp_path / "template.pptx"
    _make_template(template_path)
    provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )
    presentation = Presentation(
        name="Deck",
        slides=[Slide(id="1", replacements=[], charts=[])],
        provider=provider,
    )

    def fail_finalize(_presentation_id):
        raise RuntimeError("finalize failed")

    monkeypatch.setattr(provider, "finalize_presentation", fail_finalize)

    with pytest.raises(RuntimeError, match="finalize failed"):
        presentation.render()

    assert not (tmp_path / "Deck.pptx").exists()
    retry_provider = PowerPointProvider(
        PowerPointProviderConfig(template_path=template_path, output_dir=tmp_path)
    )
    retry_id = retry_provider.create_presentation("Deck")

    assert Path(retry_id) == tmp_path / "Deck.pptx"


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
