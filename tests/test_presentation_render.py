import logging
import time

import pandas as pd
import pytest

from slideflow.citations import CitationEntry
from slideflow.presentations.base import Presentation, Slide
from slideflow.presentations.config import CitationConfig
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


def test_render_logs_cleanup_summary_on_success(caplog):
    provider = FakeProvider(strict_cleanup=False, fail_cleanup=False)
    presentation, _chart = _build_presentation(provider)

    with caplog.at_level(logging.INFO):
        presentation.render()

    assert "Chart image cleanup completed: deleted 1/1 chart image(s)." in caplog.text


def test_render_logs_cleanup_summary_on_failure(caplog):
    provider = FakeProvider(strict_cleanup=False, fail_cleanup=True)
    presentation, _chart = _build_presentation(provider)

    with caplog.at_level(logging.WARNING):
        presentation.render()

    assert (
        "Chart image cleanup completed with 1 failure(s): deleted 0/1." in caplog.text
    )
    assert "Failed IDs: ['file-1']" in caplog.text


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


def test_render_transfers_ownership_when_configured():
    class TransferProvider(FakeProvider):
        def __init__(self):
            super().__init__(strict_cleanup=False, fail_cleanup=False)
            self.config.share_with = ["team@example.com"]
            self.config.share_role = "writer"
            self.config.transfer_ownership_to = "owner@example.com"
            self.config.transfer_ownership_strict = False
            self.share_calls = []
            self.transfer_calls = []

        def share_presentation(self, presentation_id, emails, role="writer"):
            self.share_calls.append((presentation_id, tuple(emails), role))

        def transfer_presentation_ownership(self, presentation_id, new_owner_email):
            self.transfer_calls.append((presentation_id, new_owner_email))

    provider = TransferProvider()
    presentation, _chart = _build_presentation(provider)

    result = presentation.render()

    assert provider.share_calls == [("presentation-1", ("team@example.com",), "writer")]
    assert provider.transfer_calls == [("presentation-1", "owner@example.com")]
    assert result.ownership_transfer_attempted is True
    assert result.ownership_transfer_succeeded is True
    assert result.ownership_transfer_target == "owner@example.com"
    assert result.ownership_transfer_error is None


def test_render_records_non_strict_transfer_failure():
    class TransferProvider(FakeProvider):
        def __init__(self):
            super().__init__(strict_cleanup=False, fail_cleanup=False)
            self.config.transfer_ownership_to = "owner@example.com"
            self.config.transfer_ownership_strict = False

        def transfer_presentation_ownership(self, presentation_id, new_owner_email):
            del presentation_id, new_owner_email
            raise RuntimeError()

    provider = TransferProvider()
    presentation, _chart = _build_presentation(provider)

    result = presentation.render()

    assert result.ownership_transfer_attempted is True
    assert result.ownership_transfer_succeeded is False
    assert result.ownership_transfer_error == "RuntimeError"


def test_render_raises_when_strict_transfer_fails():
    class TransferProvider(FakeProvider):
        def __init__(self):
            super().__init__(strict_cleanup=False, fail_cleanup=False)
            self.config.transfer_ownership_to = "owner@example.com"
            self.config.transfer_ownership_strict = True

        def transfer_presentation_ownership(self, presentation_id, new_owner_email):
            del presentation_id, new_owner_email
            raise RuntimeError("transfer denied")

    provider = TransferProvider()
    presentation, _chart = _build_presentation(provider)

    with pytest.raises(RenderingError, match="Ownership transfer failed"):
        presentation.render()


def test_render_emits_citations_and_calls_provider_hook():
    class CitationSource:
        type = "stub"
        name = "sales_model"

        @staticmethod
        def get_citation_entries(mode: str = "model", include_query_text: bool = False):
            metadata = {"mode": mode, "ref": "main"}
            if include_query_text:
                metadata["query_text"] = "SELECT * FROM mart.sales"
            return [
                CitationEntry(
                    source_id="dbt:sales:model:model.pkg.sales:main",
                    provider="databricks_dbt",
                    display_name="sales_model (dbt model)",
                    repo_url="https://github.com/org/repo",
                    model_path="models/marts/sales.sql",
                    metadata=metadata,
                )
            ]

        @staticmethod
        def fetch_data():
            return pd.DataFrame()

    class CitationProvider(FakeProvider):
        def __init__(self):
            super().__init__(strict_cleanup=False, fail_cleanup=False)
            self.citation_calls = []

        def render_citations(self, presentation_id, citations_by_scope, location):
            self.citation_calls.append((presentation_id, citations_by_scope, location))

    provider = CitationProvider()
    chart = FakeChart()
    chart.data_source = CitationSource()
    slide = Slide.model_construct(
        id="slide-1", title="S1", replacements=[], charts=[chart]
    )
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[slide],
        provider=provider,
        citations=CitationConfig(
            enabled=True,
            mode="model",
            location="per_slide",
            include_query_text=True,
            repo_url_template="{repo_url}/blob/{ref}/{model_path}",
        ),
    )

    result = presentation.render()

    assert result.citations_enabled is True
    assert result.citations_total_sources == 1
    assert result.citations_emitted_sources == 1
    assert result.citations_truncated is False
    assert result.citations[0]["provider"] == "databricks_dbt"
    assert result.citations[0]["metadata"]["query_text"] == "SELECT * FROM mart.sales"
    assert (
        result.citations[0]["file_url"]
        == "https://github.com/org/repo/blob/main/models/marts/sales.sql"
    )
    assert result.citations_by_scope == {
        "slide-1": ["dbt:sales:model:model.pkg.sales:main"]
    }
    assert provider.citation_calls
    assert provider.citation_calls[0][2] == "per_slide"
    assert "slide-1" in provider.citation_calls[0][1]


def test_render_aggregates_document_end_citations_to_document_scope():
    class CitationSource:
        type = "stub"
        name = "source"

        def __init__(self, source_id: str):
            self._source_id = source_id

        def get_citation_entries(
            self, mode: str = "model", include_query_text: bool = False
        ):
            del mode, include_query_text
            return [
                CitationEntry(
                    source_id=self._source_id,
                    provider="csv",
                    display_name=f"{self._source_id} (csv)",
                )
            ]

        @staticmethod
        def fetch_data():
            return pd.DataFrame()

    class CitationProvider(FakeProvider):
        def __init__(self):
            super().__init__(strict_cleanup=False, fail_cleanup=False)
            self.citation_calls = []

        def render_citations(self, presentation_id, citations_by_scope, location):
            self.citation_calls.append((presentation_id, citations_by_scope, location))

    provider = CitationProvider()
    chart_one = FakeChart()
    chart_one.data_source = CitationSource("src-1")
    chart_two = FakeChart()
    chart_two.data_source = CitationSource("src-2")

    slides = [
        Slide.model_construct(
            id="slide-1", title="S1", replacements=[], charts=[chart_one]
        ),
        Slide.model_construct(
            id="slide-2", title="S2", replacements=[], charts=[chart_two]
        ),
    ]
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=slides,
        provider=provider,
        citations=CitationConfig(
            enabled=True,
            mode="model",
            location="document_end",
        ),
    )

    result = presentation.render()

    assert result.citations_by_scope == {"__document__": ["src-1", "src-2"]}
    assert provider.citation_calls
    _, payload, location = provider.citation_calls[0]
    assert location == "document_end"
    assert "__document__" in payload


def test_create_render_context_initializes_phase_state():
    provider = FakeProvider(strict_cleanup=True, fail_cleanup=False)
    presentation, _chart = _build_presentation(provider)

    context = presentation._create_render_context(start_time=123.0)

    assert context.presentation_id == "presentation-1"
    assert context.start_time == 123.0
    assert context.strict_cleanup is True
    assert context.citations_enabled is False
    assert context.page_width_pt == 720
    assert context.page_height_pt == 540
    assert context.slides_app["pageSize"]["width"]["magnitude"] == 720
    assert context.slides_app["pageSize"]["height"]["magnitude"] == 540


def test_collect_citations_for_slides_populates_registry():
    class CitationSource:
        type = "stub"
        name = "sales_model"

        @staticmethod
        def get_citation_entries(mode: str = "model", include_query_text: bool = False):
            del mode, include_query_text
            return [
                CitationEntry(
                    source_id="stub:sales",
                    provider="databricks_dbt",
                    display_name="sales_model (dbt model)",
                )
            ]

        @staticmethod
        def fetch_data():
            return pd.DataFrame()

    provider = FakeProvider(strict_cleanup=False, fail_cleanup=False)
    chart = FakeChart()
    chart.data_source = CitationSource()
    slide = Slide.model_construct(
        id="slide-1", title="S1", replacements=[], charts=[chart]
    )
    presentation = Presentation.model_construct(
        name="Demo",
        name_fn=None,
        slides=[slide],
        provider=provider,
        citations=CitationConfig(enabled=True, location="per_slide"),
    )

    context = presentation._create_render_context(start_time=time.time())
    presentation._collect_citations_for_slides(context)
    summary = context.citation_registry.summary(
        enabled=context.citations_enabled,
        total_sources=context.citations_total_sources,
    )

    assert context.citations_total_sources == 1
    assert summary.emitted_sources == 1
    assert summary.citations_by_scope == {"slide-1": ["stub:sales"]}


def test_process_slide_content_updates_chart_and_replacement_counts():
    class CountingProvider(FakeProvider):
        def replace_text_in_slide(self, *args, **kwargs):
            del args, kwargs
            return 2

    class TextReplacement:
        type = "text"

        @staticmethod
        def get_replacement():
            return "Demo"

        @staticmethod
        def to_placeholder_values(replacement_result):
            return [("{{TITLE}}", str(replacement_result))]

        @staticmethod
        def replacement_delay_seconds():
            return 0.0

    provider = CountingProvider(strict_cleanup=False, fail_cleanup=False)
    chart = FakeChart()
    slide = Slide.model_construct(
        id="slide-1",
        title="S1",
        replacements=[TextReplacement()],
        charts=[chart],
    )
    presentation = Presentation.model_construct(
        name="Demo", name_fn=None, slides=[slide], provider=provider
    )

    context = presentation._create_render_context(start_time=time.time())
    presentation._process_slide_content(context)

    assert context.total_charts == 1
    assert context.total_replacements == 2
    assert context.uploaded_file_ids == ["file-1"]
    assert len(provider.insert_calls) == 1


def test_finalize_and_share_presentation_runs_provider_hooks():
    class SharingProvider(FakeProvider):
        def __init__(self):
            super().__init__(strict_cleanup=False, fail_cleanup=False)
            self.config.share_with = ["team@example.com"]
            self.config.share_role = "reader"
            self.share_calls = []

        def share_presentation(self, presentation_id, emails, role="writer"):
            self.share_calls.append((presentation_id, tuple(emails), role))

    provider = SharingProvider()
    presentation, _chart = _build_presentation(provider)
    context = presentation._create_render_context(start_time=time.time())

    presentation._finalize_and_share_presentation(context)

    assert provider.finalize_calls == ["presentation-1"]
    assert provider.share_calls == [("presentation-1", ("team@example.com",), "reader")]


def test_cleanup_uploaded_chart_images_strict_mode_raises_when_cleanup_fails():
    provider = FakeProvider(strict_cleanup=True, fail_cleanup=True)
    presentation, _chart = _build_presentation(provider)
    context = presentation._create_render_context(start_time=time.time())
    context.uploaded_file_ids = ["file-1"]

    with pytest.raises(RenderingError, match="Strict cleanup enabled"):
        presentation._cleanup_uploaded_chart_images(context)
