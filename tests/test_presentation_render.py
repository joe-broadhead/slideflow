import pandas as pd
import pytest

from slideflow.presentations.base import Presentation, Slide
from slideflow.utilities.exceptions import RenderingError


class FakeChart:
    def __init__(self):
        self.type = "fake"
        self.title = "chart"
        self.x = 0
        self.y = 0
        self.width = 100
        self.height = 50
        self.dimensions_format = "pt"
        self.alignment_format = None
        self.data_source = None
        self.generated_with = None

    def generate_chart_image(self, df):
        self.generated_with = df
        return b"png-bytes"


class FakeProvider:
    def __init__(self, strict_cleanup=False, fail_cleanup=False):
        self.config = type(
            "Cfg",
            (),
            {
                "strict_cleanup": strict_cleanup,
                "share_with": [],
                "share_role": "writer",
            },
        )()
        self.fail_cleanup = fail_cleanup
        self.insert_calls = []
        self.page_size = None
        self.preflight_checks = []
        self.finalize_calls = []

    def create_presentation(self, _name):
        return "presentation-1"

    def upload_chart_image(self, _presentation_id, _image_data, _filename):
        return "https://example.com/chart.png", "file-1"

    def insert_chart_to_slide(
        self,
        presentation_id,
        slide_id,
        image_url,
        x,
        y,
        width,
        height,
    ):
        self.insert_calls.append(
            {
                "presentation_id": presentation_id,
                "slide_id": slide_id,
                "image_url": image_url,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }
        )
        return None

    def replace_text_in_slide(self, *args, **kwargs):
        return 0

    def share_presentation(self, *args, **kwargs):
        return None

    def get_presentation_url(self, presentation_id):
        return f"https://example.com/{presentation_id}"

    def delete_chart_image(self, _file_id):
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed")

    def get_presentation_page_size(self, _presentation_id):
        return self.page_size

    def run_preflight_checks(self):
        return self.preflight_checks

    def finalize_presentation(self, presentation_id):
        self.finalize_calls.append(presentation_id)


def _build_presentation(provider):
    chart = FakeChart()
    slide = Slide.model_construct(
        id="slide-1", title="S1", replacements=[], charts=[chart]
    )
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[slide],
        provider=provider,
    )
    return presentation, chart


def test_render_passes_empty_dataframe_to_static_chart():
    provider = FakeProvider(strict_cleanup=False, fail_cleanup=False)
    presentation, chart = _build_presentation(provider)

    result = presentation.render()

    assert isinstance(chart.generated_with, pd.DataFrame)
    assert result.charts_generated == 1
    assert provider.finalize_calls == ["presentation-1"]


def test_render_raises_when_strict_cleanup_enabled_and_delete_fails():
    provider = FakeProvider(strict_cleanup=True, fail_cleanup=True)
    presentation, _chart = _build_presentation(provider)

    with pytest.raises(RenderingError, match="Strict cleanup enabled"):
        presentation.render()


def test_render_uses_provider_page_dimensions_for_relative_chart():
    provider = FakeProvider(strict_cleanup=False, fail_cleanup=False)
    provider.page_size = (1000, 600)
    presentation, chart = _build_presentation(provider)
    chart.dimensions_format = "relative"
    chart.x = 0
    chart.y = 0
    chart.width = 0.5
    chart.height = 0.5

    result = presentation.render()

    assert result.charts_generated == 1
    assert len(provider.insert_calls) == 1
    assert provider.insert_calls[0]["width"] == 500
    assert provider.insert_calls[0]["height"] == 300


def test_render_fails_fast_when_provider_preflight_fails():
    provider = FakeProvider(strict_cleanup=False, fail_cleanup=False)
    provider.preflight_checks = [
        ("google_credentials_present", False, "Missing credentials")
    ]
    presentation, _chart = _build_presentation(provider)

    with pytest.raises(RenderingError, match="Provider preflight checks failed"):
        presentation.render()
