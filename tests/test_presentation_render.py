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

    def create_presentation(self, _name):
        return "presentation-1"

    def upload_chart_image(self, _presentation_id, _image_data, _filename):
        return "https://example.com/chart.png", "file-1"

    def insert_chart_to_slide(self, *args, **kwargs):
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


def _build_presentation(provider):
    chart = FakeChart()
    slide = Slide.model_construct(id="slide-1", title="S1", replacements=[], charts=[chart])
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


def test_render_raises_when_strict_cleanup_enabled_and_delete_fails():
    provider = FakeProvider(strict_cleanup=True, fail_cleanup=True)
    presentation, _chart = _build_presentation(provider)

    with pytest.raises(RenderingError, match="Strict cleanup enabled"):
        presentation.render()
