"""Base classes for presentations and slides in Slideflow.

This module provides the core presentation and slide models that form the foundation
of the Slideflow presentation system. It includes result tracking, slide management,
and the main presentation rendering logic with support for concurrent operations.

The base system provides:
    - Pydantic models for type-safe presentation and slide definitions
    - Result tracking for monitoring rendering operations
    - Concurrent data fetching and chart generation for performance
    - Integration with presentation providers for platform-specific operations
    - Comprehensive error handling and logging throughout the rendering process

Key Components:
    - PresentationResult: Tracks the outcomes of complete presentation rendering
    - SlideResult: Tracks the outcomes of individual slide operations
    - Slide: Represents individual slides with charts and text replacements
    - Presentation: Main container that orchestrates the entire rendering process

The rendering process follows these phases:
    1. Presentation creation via the configured provider
    2. Concurrent data source prefetching to populate caches
    3. Chart generation and upload with positioning calculations
    4. Text replacement processing with error handling
    5. Optional presentation sharing based on provider configuration

Example:
    Creating and rendering a presentation:

    >>> from slideflow.presentations.base import Presentation, Slide
    >>> from slideflow.presentations.providers import GoogleSlidesProvider
    >>>
    >>> # Create slides with content
    >>> slides = [
    ...     Slide(
    ...         id="slide_1",
    ...         title="Overview",
    ...         replacements=[...],
    ...         charts=[...]
    ...     )
    ... ]
    >>>
    >>> # Create presentation with provider
    >>> presentation = Presentation(
    ...     name="Monthly Report",
    ...     slides=slides,
    ...     provider=provider
    ... )
    >>>
    >>> # Render the presentation
    >>> result = presentation.render()
    >>> print(f"Created presentation: {result.presentation_url}")
    >>> print(f"Generated {result.charts_generated} charts")
    >>> print(f"Made {result.replacements_made} text replacements")
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from slideflow.citations import CitationEntry, CitationRegistry, CitationSummary
from slideflow.constants import GoogleSlides, Timing
from slideflow.presentations.config import CitationConfig
from slideflow.presentations.positioning import compute_chart_dimensions
from slideflow.presentations.providers.base import PresentationProvider
from slideflow.replacements.base import BaseReplacement
from slideflow.utilities.error_messages import safe_error_line
from slideflow.utilities.exceptions import RenderingError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from slideflow.presentations.charts import BaseChart


@dataclass
class _RenderContext:
    """Mutable context shared across render orchestration phases."""

    presentation_id: str
    slides_app: Dict[str, Any]
    page_width_pt: int
    page_height_pt: int
    start_time: float
    strict_cleanup: bool
    citations_enabled: bool
    citation_registry: CitationRegistry
    total_charts: int = 0
    total_replacements: int = 0
    uploaded_file_ids: List[str] = field(default_factory=list)
    failed_cleanup_ids: List[str] = field(default_factory=list)
    original_error: Optional[Exception] = None
    ownership_transfer_attempted: bool = False
    ownership_transfer_succeeded: Optional[bool] = None
    ownership_transfer_target: Optional[str] = None
    ownership_transfer_error: Optional[str] = None
    citations_total_sources: int = 0


class PresentationResult(BaseModel):
    """Results from complete presentation rendering operations.

    This model captures comprehensive information about the outcome of rendering
    a complete presentation, including performance metrics, operation counts,
    and access information. It provides a complete audit trail of what was
    accomplished during the presentation generation process.

    The result includes both quantitative metrics (number of charts and replacements)
    and qualitative information (URLs for accessing the presentation) that can be
    used for monitoring, reporting, and user feedback.

    Attributes:
        presentation_id: Unique platform-specific identifier for the created presentation.
        presentation_url: Public URL where the presentation can be accessed and viewed.
        charts_generated: Total number of chart images successfully generated and inserted.
        replacements_made: Total number of text placeholders successfully replaced.
        render_time: Time taken to complete the entire rendering process in seconds.
        created_at: Timestamp when the presentation rendering was initiated.

    Example:
        >>> result = PresentationResult(
        ...     presentation_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        ...     presentation_url="https://docs.google.com/presentation/d/1BxiMVs0XRA5n...",
        ...     charts_generated=5,
        ...     replacements_made=12,
        ...     render_time=45.2
        ... )
        >>> print(f"Rendering completed in {result.render_time:.1f}s")
        >>> print(f"Generated {result.charts_generated} charts and {result.replacements_made} replacements")
    """

    model_config = ConfigDict(extra="forbid")

    presentation_id: Annotated[
        str, Field(..., description="Google Slides presentation ID")
    ]
    presentation_url: Annotated[
        str, Field(..., description="URL to access the presentation")
    ]
    charts_generated: Annotated[
        int, Field(..., description="Number of charts successfully generated")
    ]
    replacements_made: Annotated[
        int, Field(..., description="Number of text replacements made")
    ]
    render_time: Annotated[
        float, Field(..., description="Time taken to render presentation in seconds")
    ]
    created_at: Annotated[
        datetime,
        Field(
            default_factory=datetime.now,
            description="Timestamp when presentation was created",
        ),
    ]
    ownership_transfer_attempted: Annotated[
        bool,
        Field(
            default=False,
            description="Whether ownership transfer was explicitly requested and attempted",
        ),
    ]
    ownership_transfer_succeeded: Annotated[
        Optional[bool],
        Field(
            default=None,
            description="Ownership transfer result when attempted, otherwise null",
        ),
    ]
    ownership_transfer_target: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Ownership transfer target email when configured",
        ),
    ]
    ownership_transfer_error: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Single-line transfer error when ownership transfer fails",
        ),
    ]
    citations_enabled: Annotated[
        bool,
        Field(default=False, description="Whether citation collection was enabled"),
    ]
    citations_total_sources: Annotated[
        int,
        Field(
            default=0,
            description="Total citation entries encountered before truncation/dedupe",
        ),
    ]
    citations_emitted_sources: Annotated[
        int,
        Field(default=0, description="Number of citation entries emitted"),
    ]
    citations_truncated: Annotated[
        bool,
        Field(
            default=False,
            description="Whether citation output was truncated by max_items",
        ),
    ]
    citations: Annotated[
        List[Dict[str, Any]],
        Field(default_factory=list, description="Emitted citation entries"),
    ]
    citations_by_scope: Annotated[
        Dict[str, List[str]],
        Field(
            default_factory=dict,
            description="Citation source IDs grouped by slide/section scope",
        ),
    ]


class SlideResult(BaseModel):
    """Results from individual slide rendering operations.

    This model tracks the outcomes of operations performed on a single slide
    within a presentation, providing detailed information about chart insertions
    and text replacements for monitoring and debugging purposes.

    The slide result enables granular tracking of presentation generation,
    allowing developers to identify which slides had issues or required
    the most processing time during rendering operations.

    Attributes:
        slide_id: Unique identifier for the slide within the presentation.
        charts_count: Number of chart objects that were processed for this slide.
        replacements_count: Number of text replacement objects processed for this slide.
        chart_images: List of chart titles or descriptions for reference and debugging.

    Example:
        >>> slide_result = SlideResult(
        ...     slide_id="slide_1",
        ...     charts_count=2,
        ...     replacements_count=4,
        ...     chart_images=["Revenue Chart", "Growth Metrics"]
        ... )
        >>> print(f"Slide {slide_result.slide_id}: {slide_result.charts_count} charts, {slide_result.replacements_count} replacements")
    """

    model_config = ConfigDict(extra="forbid")

    slide_id: Annotated[str, Field(..., description="Slide ID")]
    charts_count: Annotated[
        int, Field(..., description="Number of charts on this slide")
    ]
    replacements_count: Annotated[
        int, Field(..., description="Number of replacements on this slide")
    ]
    chart_images: Annotated[List[str], Field(..., description="List of chart titles")]


class Slide(BaseModel):
    """Individual slide container with charts and text replacements.

    This model represents a single slide within a presentation, containing all
    the content elements that need to be rendered including charts and text
    replacements. It provides methods for building platform-specific API requests
    and tracking rendering results.

    The Slide class handles the translation between Slideflow's generic content
    model and platform-specific presentation APIs, generating appropriate
    request objects for chart insertion and text replacement operations.

    Attributes:
        id: Platform-specific unique identifier for the slide.
        title: Optional human-readable title for documentation and debugging.
        replacements: List of text replacement objects to process on this slide.
        charts: List of chart objects to generate and insert into this slide.

    Example:
        >>> from slideflow.charts.base import BaseChart
        >>> from slideflow.replacements.base import BaseReplacement
        >>>
        >>> slide = Slide(
        ...     id="slide_123",
        ...     title="Monthly Overview",
        ...     replacements=[text_replacement],
        ...     charts=[revenue_chart, growth_chart]
        ... )
        >>>
        >>> # Build API requests for this slide
        >>> chart_urls = {"chart_0_123": "https://example.com/chart1.png"}
        >>> requests = slide.build_update_requests(chart_urls)
        >>> print(f"Generated {len(requests)} API requests")
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    id: Annotated[str, Field(..., description="Slide ID in Google Slides")]
    title: Annotated[
        Optional[str], Field(None, description="Slide title for documentation")
    ]
    replacements: Annotated[
        List[BaseReplacement],
        Field(default_factory=list, description="Text replacements for this slide"),
    ]
    charts: Annotated[
        List["BaseChart"],
        Field(default_factory=list, description="Charts to generate for this slide"),
    ]

    def build_update_requests(
        self,
        chart_urls: Dict[str, str],
        page_width_pt: int = GoogleSlides.STANDARD_WIDTH_POINTS,
        page_height_pt: int = GoogleSlides.STANDARD_HEIGHT_POINTS,
    ) -> List[Dict[str, Any]]:
        """Build platform-specific API requests for updating this slide.

        Generates a list of API request objects that can be executed to update
        the slide with all its content including text replacements and chart
        insertions. The requests are structured for Google Slides API but could
        be adapted for other platforms.

        This method handles the translation between Slideflow's generic content
        model and the specific API format required by the presentation platform,
        including coordinate transformations and request formatting.

        Args:
            chart_urls: Dictionary mapping chart identifiers to their public URLs.
                The keys should match the format "chart_{index}_{object_id}" and
                values should be publicly accessible image URLs.

        Returns:
            List of API request dictionaries ready for execution via batchUpdate.
            Each request contains either a replaceAllText or createImage operation
            with all necessary parameters for the platform API.

        Example:
            >>> chart_urls = {
            ...     "chart_0_abc123": "https://drive.google.com/uc?id=image1",
            ...     "chart_1_def456": "https://drive.google.com/uc?id=image2"
            ... }
            >>> requests = slide.build_update_requests(chart_urls)
            >>> for req in requests:
            ...     if 'replaceAllText' in req:
            ...         print(f"Text replacement: {req['replaceAllText']['containsText']['text']}")
            ...     elif 'createImage' in req:
            ...         print(f"Image insertion: {req['createImage']['url']}")
        """
        requests = []

        for replacement in self.replacements:
            replacement_result = replacement.get_replacement()
            for placeholder, value in replacement.to_placeholder_values(
                replacement_result
            ):
                requests.append(
                    {
                        "replaceAllText": {
                            "containsText": {"text": placeholder, "matchCase": True},
                            "replaceText": str(value),
                            "pageObjectIds": [self.id],
                        }
                    }
                )

        slides_app = {
            "pageSize": {
                "width": {"magnitude": page_width_pt, "unit": "PT"},
                "height": {"magnitude": page_height_pt, "unit": "PT"},
            }
        }

        # Build chart insertion requests
        for i, chart in enumerate(self.charts):
            chart_id = f"chart_{i}_{id(chart)}"
            if chart_id in chart_urls:
                # Compute chart dimensions using positioning utilities

                x_pt, y_pt, width_pt, height_pt = compute_chart_dimensions(
                    x=chart.x,
                    y=chart.y,
                    width=chart.width,
                    height=chart.height,
                    dimensions_format=chart.dimensions_format,
                    alignment_format=chart.alignment_format,
                    slides_app=slides_app,
                    page_width_pt=page_width_pt,
                    page_height_pt=page_height_pt,
                )

                # Create chart image with computed positioning and sizing
                object_id = f"chart_{self.id}_{i}_{hex(id(chart))[2:8]}"
                requests.append(
                    {
                        "createImage": {
                            "objectId": object_id,
                            "url": chart_urls[chart_id],
                            "elementProperties": {
                                "pageObjectId": self.id,
                                "size": {
                                    "height": {"magnitude": height_pt, "unit": "PT"},
                                    "width": {"magnitude": width_pt, "unit": "PT"},
                                },
                                "transform": {
                                    "translateX": x_pt,
                                    "translateY": y_pt,
                                    "scaleX": 1,
                                    "scaleY": 1,
                                    "unit": "PT",
                                },
                            },
                        }
                    }
                )

        return requests

    def get_result(self) -> SlideResult:
        """Generate a result summary for this slide's content.

        Creates a SlideResult object that summarizes the content and operations
        that would be performed on this slide, providing metrics for monitoring
        and reporting purposes.

        Returns:
            SlideResult containing counts and metadata about this slide's content.

        Example:
            >>> slide_result = slide.get_result()
            >>> print(f"Slide has {slide_result.charts_count} charts and {slide_result.replacements_count} replacements")
        """
        return SlideResult(
            slide_id=self.id,
            charts_count=len(self.charts),
            replacements_count=len(self.replacements),
            chart_images=[
                chart.title or f"Chart {i+1}" for i, chart in enumerate(self.charts)
            ],
        )


class Presentation(BaseModel):
    """Main presentation container and orchestrator for content rendering.

    This class represents a complete presentation and provides the primary interface
    for rendering presentations with all their content including slides, charts,
    and text replacements. It orchestrates the entire rendering process from
    data fetching through final presentation sharing.

    The Presentation class handles:
    - Presentation creation via the configured provider
    - Concurrent data source prefetching for performance optimization
    - Chart generation and upload with precise positioning
    - Text replacement processing with comprehensive error handling
    - Optional presentation sharing based on provider configuration

    The rendering process is designed for performance and reliability, using
    concurrent operations where possible and providing detailed error reporting
    for troubleshooting presentation generation issues.

    Attributes:
        name: Human-readable name for the presentation.
        slides: List of Slide objects containing the presentation content.
        provider: Platform-specific provider for presentation operations.

    Example:
        >>> from slideflow.presentations.providers import GoogleSlidesProvider
        >>>
        >>> # Create slides with content
        >>> slides = [
        ...     Slide(
        ...         id="slide_1",
        ...         title="Overview",
        ...         charts=[revenue_chart],
        ...         replacements=[company_name_replacement]
        ...     ),
        ...     Slide(
        ...         id="slide_2",
        ...         title="Details",
        ...         charts=[breakdown_chart],
        ...         replacements=[month_replacement]
        ...     )
        ... ]
        >>>
        >>> # Create and render presentation
        >>> presentation = Presentation(
        ...     name="Q4 Financial Report",
        ...     slides=slides,
        ...     provider=google_slides_provider
        ... )
        >>>
        >>> result = presentation.render()
        >>> print(f"Presentation URL: {result.presentation_url}")
        >>> print(f"Completed in {result.render_time:.1f} seconds")
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: Annotated[str, Field(..., description="Presentation name")]
    name_fn: Annotated[
        Optional[Callable], Field(None, description="Optional function for name")
    ]
    slides: Annotated[
        List[Slide], Field(..., description="List of slides in the presentation")
    ]
    provider: Annotated[
        PresentationProvider,
        Field(..., exclude=True, description="Presentation provider instance"),
    ]
    citations: Annotated[
        CitationConfig,
        Field(default_factory=CitationConfig, description="Citation configuration"),
    ]

    @model_validator(mode="after")
    def apply_name_fn(self):
        if self.name_fn:
            self.name = self.name_fn(self.name)
        return self

    @staticmethod
    def _to_slides_app_dimensions(
        page_width_pt: int, page_height_pt: int
    ) -> Dict[str, Any]:
        return {
            "pageSize": {
                "width": {"magnitude": page_width_pt, "unit": "PT"},
                "height": {"magnitude": page_height_pt, "unit": "PT"},
            }
        }

    def _resolve_page_dimensions(self, presentation_id: str) -> Tuple[int, int]:
        page_width_pt = GoogleSlides.STANDARD_WIDTH_POINTS
        page_height_pt = GoogleSlides.STANDARD_HEIGHT_POINTS

        get_page_size = getattr(self.provider, "get_presentation_page_size", None)
        provider_dimensions = (
            get_page_size(presentation_id) if callable(get_page_size) else None
        )
        if provider_dimensions:
            page_width_pt, page_height_pt = provider_dimensions

        return page_width_pt, page_height_pt

    def _run_provider_preflight(self) -> None:
        failed_checks = []
        run_preflight = getattr(self.provider, "run_preflight_checks", None)
        preflight_checks = run_preflight() if callable(run_preflight) else []
        for check_name, ok, detail in preflight_checks:
            if not ok:
                failed_checks.append(f"{check_name}: {detail}")

        if failed_checks:
            raise RenderingError(
                "Provider preflight checks failed: " + "; ".join(failed_checks)
            )

    @staticmethod
    def _collect_slide_sources(slide: Slide) -> List[Any]:
        """Collect data sources referenced by charts/replacements on a slide."""
        collected: List[Any] = []

        for chart in slide.charts:
            source = getattr(chart, "data_source", None)
            if source is not None:
                collected.append(source)

        for replacement in slide.replacements:
            collected.extend(replacement.get_referenced_data_sources())

        return collected

    def _create_render_context(self, start_time: float) -> _RenderContext:
        """Create render context after provider preflight and presentation creation."""
        self._run_provider_preflight()
        presentation_id = self.provider.create_presentation(self.name)
        page_width_pt, page_height_pt = self._resolve_page_dimensions(presentation_id)

        return _RenderContext(
            presentation_id=presentation_id,
            slides_app=self._to_slides_app_dimensions(page_width_pt, page_height_pt),
            page_width_pt=page_width_pt,
            page_height_pt=page_height_pt,
            start_time=start_time,
            strict_cleanup=bool(
                getattr(getattr(self.provider, "config", None), "strict_cleanup", False)
            ),
            citations_enabled=bool(self.citations.enabled),
            citation_registry=CitationRegistry(
                max_items=self.citations.max_items,
                dedupe=self.citations.dedupe,
            ),
        )

    def _collect_citations_for_slides(self, context: _RenderContext) -> None:
        """Collect citation entries from slide data sources into the render registry."""
        if not context.citations_enabled:
            return

        for slide in self.slides:
            slide_sources = self._collect_slide_sources(slide)
            scope_id = (
                "__document__"
                if self.citations.location == "document_end"
                else slide.id
            )
            for source in slide_sources:
                get_citations = getattr(source, "get_citation_entries", None)
                if not callable(get_citations):
                    continue
                try:
                    try:
                        entries = get_citations(
                            mode=self.citations.mode,
                            include_query_text=self.citations.include_query_text,
                        )
                    except TypeError:
                        # Backward compatibility for custom connectors that only accept ``mode``.
                        entries = get_citations(mode=self.citations.mode)
                except Exception as citation_error:
                    logger.warning(
                        "Citation generation failed for source '%s': %s",
                        getattr(source, "name", type(source).__name__),
                        citation_error,
                    )
                    continue

                for entry in entries:
                    try:
                        citation_entry = (
                            entry
                            if isinstance(entry, CitationEntry)
                            else CitationEntry.model_validate(entry)
                        )
                    except Exception as citation_entry_error:
                        logger.warning(
                            "Skipping invalid citation entry for source '%s': %s",
                            getattr(source, "name", type(source).__name__),
                            citation_entry_error,
                        )
                        continue
                    template = self.citations.repo_url_template
                    if template:
                        try:
                            citation_entry = citation_entry.model_copy(
                                update={
                                    "file_url": template.format(
                                        repo_url=citation_entry.repo_url or "",
                                        model_path=citation_entry.model_path or "",
                                        model_unique_id=citation_entry.model_unique_id
                                        or "",
                                        ref=str(citation_entry.metadata.get("ref", "")),
                                    )
                                }
                            )
                        except Exception as template_error:
                            logger.warning(
                                "Citation repo_url_template formatting failed for source '%s': %s",
                                getattr(source, "name", type(source).__name__),
                                template_error,
                            )
                    context.citations_total_sources += 1
                    context.citation_registry.add(citation_entry, scope_id=scope_id)

    def _process_single_chart(
        self, context: _RenderContext, slide: Slide, chart: "BaseChart"
    ) -> None:
        """Generate, upload, and insert a single chart with retry behavior."""
        max_retries = Timing.PRESENTATION_CHART_MAX_RETRIES
        base_retry_delay_s = Timing.PRESENTATION_CHART_RETRY_DELAY_S
        backoff_multiplier = Timing.PRESENTATION_CHART_RETRY_BACKOFF_MULTIPLIER

        for attempt in range(max_retries):
            try:
                df = (
                    chart.data_source.fetch_data()
                    if chart.data_source
                    else pd.DataFrame()
                )
                image_data = chart.generate_chart_image(df)
                image_url, file_id = self.provider.upload_chart_image(
                    context.presentation_id,
                    image_data,
                    f"chart_{chart.title or 'untitled'}.png",
                )
                if file_id:
                    context.uploaded_file_ids.append(file_id)

                x_pt, y_pt, width_pt, height_pt = compute_chart_dimensions(
                    x=chart.x,
                    y=chart.y,
                    width=chart.width,
                    height=chart.height,
                    dimensions_format=chart.dimensions_format,
                    alignment_format=chart.alignment_format,
                    slides_app=context.slides_app,
                    page_width_pt=context.page_width_pt,
                    page_height_pt=context.page_height_pt,
                )

                self.provider.insert_chart_to_slide(
                    context.presentation_id,
                    slide.id,
                    image_url,
                    x_pt,
                    y_pt,
                    width_pt,
                    height_pt,
                )
                context.total_charts += 1
                return
            except Exception as error:
                if attempt < max_retries - 1:
                    delay_seconds = base_retry_delay_s * (backoff_multiplier**attempt)
                    logger.warning(
                        "Chart processing failed for '%s' on slide '%s' (attempt %d/%d). Retrying in %s seconds. Error: %s",
                        chart.title or chart.type,
                        slide.id,
                        attempt + 1,
                        max_retries,
                        delay_seconds,
                        error,
                    )
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                    continue

                logger.error(
                    "Chart processing failed for '%s' on slide '%s' after %d attempts. Inserting error placeholder. Error: %s",
                    chart.title or chart.type,
                    slide.id,
                    max_retries,
                    error,
                )
                try:
                    x_pt, y_pt, width_pt, height_pt = compute_chart_dimensions(
                        x=chart.x,
                        y=chart.y,
                        width=chart.width,
                        height=chart.height,
                        dimensions_format=chart.dimensions_format,
                        alignment_format=chart.alignment_format,
                        slides_app=context.slides_app,
                        page_width_pt=context.page_width_pt,
                        page_height_pt=context.page_height_pt,
                    )
                    error_image_url = "https://drive.google.com/uc?id=10geCrUpKZmQBesbhjtepZ9NexE-HRkn4"
                    self.provider.insert_chart_to_slide(
                        context.presentation_id,
                        slide.id,
                        error_image_url,
                        x=x_pt,
                        y=y_pt,
                        width=width_pt,
                        height=height_pt,
                    )
                    logger.info(
                        "Inserted error placeholder for chart on slide '%s'", slide.id
                    )
                except Exception as image_error:
                    logger.error(
                        "Failed to insert error placeholder for chart on slide '%s': %s",
                        slide.id,
                        image_error,
                    )
                return

    def _process_slide_charts(self, context: _RenderContext, slide: Slide) -> None:
        for chart in slide.charts:
            self._process_single_chart(context, slide, chart)

    def _process_slide_replacements(
        self, context: _RenderContext, slide: Slide
    ) -> None:
        """Process text/table replacements for a single slide."""
        for replacement in slide.replacements:
            try:
                replacement_result = replacement.get_replacement()
                delay_seconds = replacement.replacement_delay_seconds()
                for placeholder, value in replacement.to_placeholder_values(
                    replacement_result
                ):
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                    replacements_made = self.provider.replace_text_in_slide(
                        context.presentation_id,
                        slide.id,
                        placeholder,
                        str(value),
                    )
                    context.total_replacements += replacements_made
                    logger.debug(
                        "Processed replacement for %s: %d occurrences",
                        placeholder,
                        replacements_made,
                    )
            except Exception as error:
                replacement_type = getattr(
                    replacement, "type", type(replacement).__name__
                )
                placeholder = getattr(replacement, "placeholder", "unknown")
                logger.error(
                    "Failed to process %s replacement '%s': %s",
                    replacement_type,
                    placeholder,
                    error,
                )
                continue

    def _process_slide_content(self, context: _RenderContext) -> None:
        """Render charts and replacements across all slides in declaration order."""
        for slide in self.slides:
            self._process_slide_charts(context, slide)
            self._process_slide_replacements(context, slide)

    def _summarize_and_render_citations(
        self, context: _RenderContext
    ) -> CitationSummary:
        """Summarize citation registry and invoke provider rendering hook when enabled."""
        citation_summary = context.citation_registry.summary(
            enabled=context.citations_enabled,
            total_sources=context.citations_total_sources,
        )
        if not (context.citations_enabled and citation_summary.citations):
            return citation_summary

        entry_by_source_id = {
            entry.source_id: entry for entry in citation_summary.citations
        }
        provider_citations_by_scope: Dict[str, List[Dict[str, Any]]] = {}
        for scope_id, source_ids in citation_summary.citations_by_scope.items():
            provider_citations_by_scope[scope_id] = [
                entry_by_source_id[source_id].model_dump(mode="json")
                for source_id in source_ids
                if source_id in entry_by_source_id
            ]
        if (
            self.citations.location == "document_end"
            and "__document__" not in provider_citations_by_scope
        ):
            provider_citations_by_scope["__document__"] = [
                entry.model_dump(mode="json") for entry in citation_summary.citations
            ]

        render_citations = getattr(self.provider, "render_citations", None)
        if callable(render_citations):
            try:
                render_citations(
                    context.presentation_id,
                    provider_citations_by_scope,
                    self.citations.location,
                )
            except Exception as citation_render_error:
                logger.warning(
                    "Provider citation rendering failed: %s", citation_render_error
                )
        else:
            logger.debug(
                "Provider '%s' does not implement citation rendering",
                type(self.provider).__name__,
            )

        return citation_summary

    def _finalize_and_share_presentation(self, context: _RenderContext) -> None:
        """Run provider finalization and optional share calls."""
        finalize_presentation = getattr(self.provider, "finalize_presentation", None)
        if callable(finalize_presentation):
            finalize_presentation(context.presentation_id)

        if (
            hasattr(self.provider, "config")
            and hasattr(self.provider.config, "share_with")
            and self.provider.config.share_with
        ):
            self.provider.share_presentation(
                context.presentation_id,
                self.provider.config.share_with,
                getattr(self.provider.config, "share_role", "writer"),
            )

    def _apply_ownership_transfer(self, context: _RenderContext) -> None:
        """Transfer ownership when configured, preserving strict/non-strict behavior."""
        transfer_owner = getattr(
            getattr(self.provider, "config", None), "transfer_ownership_to", None
        )
        if not transfer_owner:
            return

        context.ownership_transfer_attempted = True
        context.ownership_transfer_target = transfer_owner
        transfer_strict = bool(
            getattr(
                getattr(self.provider, "config", None),
                "transfer_ownership_strict",
                False,
            )
        )
        transfer_method = getattr(
            self.provider, "transfer_presentation_ownership", None
        )

        if not callable(transfer_method):
            context.ownership_transfer_succeeded = False
            context.ownership_transfer_error = (
                "Ownership transfer is not supported by provider "
                f"'{type(self.provider).__name__}'"
            )
            logger.warning(context.ownership_transfer_error)
            if transfer_strict:
                raise RenderingError(context.ownership_transfer_error)
            return

        try:
            transfer_method(context.presentation_id, transfer_owner)
            context.ownership_transfer_succeeded = True
        except Exception as transfer_error:  # pragma: no cover - guarded via tests
            context.ownership_transfer_succeeded = False
            context.ownership_transfer_error = safe_error_line(transfer_error)
            logger.error(
                "Ownership transfer failed for '%s' -> '%s': %s",
                context.presentation_id,
                transfer_owner,
                context.ownership_transfer_error,
            )
            if transfer_strict:
                raise RenderingError(
                    "Ownership transfer failed: " f"{context.ownership_transfer_error}"
                ) from transfer_error

    def _build_presentation_result(
        self, context: _RenderContext, citation_summary: CitationSummary
    ) -> PresentationResult:
        """Build final presentation result payload from render context."""
        render_time = time.time() - context.start_time
        return PresentationResult(
            presentation_id=context.presentation_id,
            presentation_url=self.provider.get_presentation_url(
                context.presentation_id
            ),
            charts_generated=context.total_charts,
            replacements_made=context.total_replacements,
            render_time=render_time,
            created_at=datetime.now(),
            ownership_transfer_attempted=context.ownership_transfer_attempted,
            ownership_transfer_succeeded=context.ownership_transfer_succeeded,
            ownership_transfer_target=context.ownership_transfer_target,
            ownership_transfer_error=context.ownership_transfer_error,
            citations_enabled=citation_summary.enabled,
            citations_total_sources=citation_summary.total_sources,
            citations_emitted_sources=citation_summary.emitted_sources,
            citations_truncated=citation_summary.truncated,
            citations=[
                citation.model_dump(mode="json")
                for citation in citation_summary.citations
            ],
            citations_by_scope=citation_summary.citations_by_scope,
        )

    def _cleanup_uploaded_chart_images(self, context: _RenderContext) -> None:
        """Delete uploaded chart images and enforce strict cleanup when configured."""
        if context.uploaded_file_ids:
            logger.info(
                "Cleaning up %d uploaded chart images.", len(context.uploaded_file_ids)
            )
            for file_id in context.uploaded_file_ids:
                try:
                    self.provider.delete_chart_image(file_id)
                except Exception as cleanup_error:
                    context.failed_cleanup_ids.append(file_id)
                    logger.warning(
                        "Failed to delete chart image %s: %s",
                        file_id,
                        cleanup_error,
                    )

            deleted_cleanup_count = len(context.uploaded_file_ids) - len(
                context.failed_cleanup_ids
            )
            if context.failed_cleanup_ids:
                logger.warning(
                    "Chart image cleanup completed with %d failure(s): deleted %d/%d. "
                    "Failed IDs: %s",
                    len(context.failed_cleanup_ids),
                    deleted_cleanup_count,
                    len(context.uploaded_file_ids),
                    context.failed_cleanup_ids,
                )
            else:
                logger.info(
                    "Chart image cleanup completed: deleted %d/%d chart image(s).",
                    deleted_cleanup_count,
                    len(context.uploaded_file_ids),
                )

        if (
            context.strict_cleanup
            and context.failed_cleanup_ids
            and context.original_error is None
        ):
            raise RenderingError(
                f"Strict cleanup enabled and {len(context.failed_cleanup_ids)} chart image(s) "
                f"could not be deleted: {context.failed_cleanup_ids}"
            )

    def render(self) -> PresentationResult:
        """Render the complete presentation with all content and styling."""
        context: Optional[_RenderContext] = None
        try:
            context = self._create_render_context(start_time=time.time())
            self._prefetch_data_sources()
            self._collect_citations_for_slides(context)
            self._process_slide_content(context)
            citation_summary = self._summarize_and_render_citations(context)
            self._finalize_and_share_presentation(context)
            self._apply_ownership_transfer(context)
            return self._build_presentation_result(context, citation_summary)
        except Exception as error:
            if context is not None:
                context.original_error = error
            raise
        finally:
            if context is not None:
                self._cleanup_uploaded_chart_images(context)

    def get_slide(self, slide_id: str) -> Optional[Slide]:
        """Retrieve a slide by its unique identifier.

        Searches through the presentation's slides to find the slide with the
        matching identifier. This is useful for accessing specific slides for
        updates or content inspection.

        Args:
            slide_id: Platform-specific unique identifier for the slide to retrieve.

        Returns:
            Slide object if a slide with the specified ID is found, None otherwise.

        Example:
            >>> presentation = Presentation(name="Report", slides=slides, provider=provider)
            >>> slide = presentation.get_slide("slide_1")
            >>> if slide:
            ...     print(f"Found slide: {slide.title}")
            ...     print(f"Charts: {len(slide.charts)}, Replacements: {len(slide.replacements)}")
            ... else:
            ...     print("Slide not found")
        """
        for slide in self.slides:
            if slide.id == slide_id:
                return slide
        return None

    def _execute_concurrent_tasks(
        self,
        items: List[Tuple[Any, Any]],
        task_func: Callable[[Any], Any],
        task_name: str,
        max_workers: int = 10,
        collect_results: bool = False,
    ) -> List[Any]:
        """Execute a list of tasks concurrently with proper error handling and logging.

        Provides a reusable pattern for executing multiple similar tasks concurrently
        using ThreadPoolExecutor, with comprehensive error handling and performance
        logging. This method is used internally for operations like data fetching
        and chart generation that can benefit from parallelization.

        The method ensures that:
        - Tasks are executed with controlled concurrency limits
        - Errors in individual tasks are properly logged and re-raised
        - Performance metrics are captured for monitoring
        - Results are optionally collected and returned

        Args:
            items: List of (identifier, item) tuples where identifier is used for
                logging and item is passed to task_func for processing.
            task_func: Callable that takes an item and performs the desired operation.
                Should be thread-safe and handle its own error conditions.
            task_name: Human-readable name for the task type, used in logging messages
                for debugging and monitoring purposes.
            max_workers: Maximum number of concurrent threads to use. Will be capped
                at the number of items to avoid creating unnecessary threads.
            collect_results: Whether to collect return values from task_func and
                return them as a list. Set to False for operations that don't return
                meaningful results to save memory.

        Returns:
            List of (identifier, result) tuples if collect_results=True, containing
            the results from each successful task execution. Returns empty list if
            collect_results=False or if no items were provided.

        Raises:
            Exception: Re-raises any exception that occurs during task execution.
                The original exception is preserved with additional logging context.

        Example:
            >>> # Data fetching example
            >>> data_sources = [("source1", source1_obj), ("source2", source2_obj)]
            >>> presentation._execute_concurrent_tasks(
            ...     items=data_sources,
            ...     task_func=lambda source: source.fetch_data(),
            ...     task_name="data fetch",
            ...     max_workers=5,
            ...     collect_results=False
            ... )
        """
        logger = get_logger(__name__)

        if not items:
            return []

        results: List[Tuple[Any, Any]] = []

        logger.info(f"Executing {len(items)} {task_name} tasks concurrently")

        with ThreadPoolExecutor(max_workers=min(len(items), max_workers)) as executor:
            # Submit all tasks
            future_to_item: Dict[Any, Tuple[Any, Any]] = {
                executor.submit(task_func, item): (identifier, item)
                for identifier, item in items
            }

            # Process completed tasks
            for future in as_completed(future_to_item):
                identifier, item = future_to_item[future]
                try:
                    result = future.result()
                    if collect_results:
                        results.append((identifier, result))
                    logger.debug(f"Successfully completed {task_name}: {identifier}")
                except Exception as e:
                    logger.error(f"Failed to execute {task_name} '{identifier}': {e}")
                    raise

        return results if collect_results else []

    def _prefetch_data_sources(self) -> None:
        """Pre-fetch all unique data sources to populate the cache system.

        Identifies all unique data sources used across slides and replacements,
        then fetches their data concurrently to populate the cache. This optimization
        reduces redundant data fetching during the actual rendering process and
        improves overall performance.

        The method:
        1. Scans all slides for data sources in both replacements and charts
        2. Deduplicates sources based on type and name to avoid redundant fetches
        3. Executes concurrent data fetching using the thread pool
        4. Populates the cache for subsequent use during rendering

        This prefetching strategy is particularly beneficial when multiple slides
        or replacements use the same data source, as it ensures the data is only
        fetched once regardless of usage frequency.

        Example:
            The method automatically handles scenarios like:
            - Multiple charts using the same database query
            - Text replacements and charts sharing data sources
            - Complex presentations with many repeated data references
        """
        # Collect all unique data sources
        unique_sources = []
        seen_sources = set()

        for slide in self.slides:
            # Collect from replacements
            for replacement in slide.replacements:
                for source in replacement.get_referenced_data_sources():
                    source_key = (source.type, source.name)
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        unique_sources.append((source.name, source))

            for chart in slide.charts:
                if hasattr(chart, "data_source") and chart.data_source:
                    source_key = (chart.data_source.type, chart.data_source.name)
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        unique_sources.append(
                            (chart.data_source.name, chart.data_source)
                        )

        self._execute_concurrent_tasks(
            items=unique_sources,
            task_func=lambda source: source.fetch_data(),
            task_name="data source fetch",
            max_workers=10,
            collect_results=False,
        )

    def _generate_and_upload_charts(self) -> Tuple[Dict[str, str], List[str]]:
        """Generate all chart images and upload them to the presentation platform.

        Iterates through all slides and charts, generates image representations
        of each chart, and uploads them to the platform's storage system. Returns
        mappings and identifiers needed for chart insertion and cleanup operations.

        This method handles the complete chart processing pipeline:
        1. Iterates through all slides and their associated charts
        2. Generates chart images using the chart's render methods
        3. Uploads images to platform storage (e.g., Google Drive)
        4. Creates public URLs for chart insertion into slides
        5. Tracks file IDs for potential cleanup operations

        Returns:
            Tuple containing:
            - chart_urls: Dictionary mapping chart identifiers to their public URLs
            - file_ids: List of platform file IDs for uploaded images (for cleanup)

        Raises:
            RenderingError: If Google Slides service is not available.
            UploadError: If chart image upload fails.

        Note:
            This method assumes Google Slides service is available and configured.
            The chart URLs are used later for inserting images into specific slides.

        Example:
            >>> chart_urls, file_ids = presentation._generate_and_upload_charts()
            >>> print(f"Uploaded {len(chart_urls)} charts with IDs: {file_ids}")
        """
        drive_service = getattr(self.provider, "drive_service", None)
        if drive_service is None:
            raise RenderingError(
                "Google Slides service is required for chart generation"
            )

        chart_urls = {}
        file_ids = []

        for slide in self.slides:
            for i, chart in enumerate(slide.charts):
                # Generate public URL and file ID for chart
                public_url, file_id = chart.generate_public_url(drive_service)
                chart_id = f"chart_{i}_{id(chart)}"
                chart_urls[chart_id] = public_url
                file_ids.append(file_id)

        return chart_urls, file_ids
