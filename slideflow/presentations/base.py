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
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Annotated, Tuple

from slideflow.utilities.logging import get_logger
from slideflow.replacements.base import BaseReplacement
from slideflow.utilities.exceptions import RenderingError
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.presentations.providers.base import PresentationProvider
from slideflow.presentations.positioning import compute_chart_dimensions

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
    
    model_config = ConfigDict(extra = "forbid")
    
    presentation_id: Annotated[str, Field(..., description = "Google Slides presentation ID")]
    presentation_url: Annotated[str, Field(..., description = "URL to access the presentation")]
    charts_generated: Annotated[int, Field(..., description = "Number of charts successfully generated")]
    replacements_made: Annotated[int, Field(..., description = "Number of text replacements made")]
    render_time: Annotated[float, Field(..., description = "Time taken to render presentation in seconds")]
    created_at: Annotated[datetime, Field(default_factory = datetime.now, description = "Timestamp when presentation was created")]

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
    
    model_config = ConfigDict(extra = "forbid")
    
    slide_id: Annotated[str, Field(..., description = "Slide ID")]
    charts_count: Annotated[int, Field(..., description = "Number of charts on this slide")]
    replacements_count: Annotated[int, Field(..., description = "Number of replacements on this slide")]
    chart_images: Annotated[List[str], Field(..., description = "List of chart titles")]

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
    
    model_config = ConfigDict(extra = "forbid", arbitrary_types_allowed = True)
    
    id: Annotated[str, Field(..., description = "Slide ID in Google Slides")]
    title: Annotated[Optional[str], Field(None, description = "Slide title for documentation")]
    replacements: Annotated[List[BaseReplacement], Field(default_factory = list, description = "Text replacements for this slide")]
    charts: Annotated[List["BaseChart"], Field(default_factory = list, description = "Charts to generate for this slide")]
    
    def build_update_requests(self, chart_urls: Dict[str, str]) -> List[Dict[str, Any]]:
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

            if hasattr(replacement, 'placeholder'):
                # Text and AI text replacements
                requests.append({
                    'replaceAllText': {
                        'containsText': {
                            'text': replacement.placeholder,
                            'matchCase': True
                        },
                        'replaceText': str(replacement_result),
                        'pageObjectIds': [self.id]
                    }
                })
            elif hasattr(replacement, 'prefix'):
                # Table replacements return a dictionary of placeholder->value
                if isinstance(replacement_result, dict):
                    for placeholder, value in replacement_result.items():
                        requests.append({
                            'replaceAllText': {
                                'containsText': {
                                    'text': placeholder,
                                    'matchCase': True
                                },
                                'replaceText': str(value),
                                'pageObjectIds': [self.id]
                            }
                        })
        
        # Build chart insertion requests
        for i, chart in enumerate(self.charts):
            chart_id = f"chart_{i}_{id(chart)}"
            if chart_id in chart_urls:
                # Compute chart dimensions using positioning utilities
                
                x_pt, y_pt, width_pt, height_pt = compute_chart_dimensions(
                    x = chart.x,
                    y = chart.y,
                    width = chart.width,
                    height = chart.height,
                    dimensions_format = chart.dimensions_format,
                    alignment_format = chart.alignment_format,
                    slides_app = None,  # TODO: Get slide dimensions from template
                    page_width_pt = 720,  # Standard Google Slides width in points
                    page_height_pt = 540  # Standard Google Slides height in points
                )
                
                # Create chart image with computed positioning and sizing
                object_id = f"chart_{self.id}_{i}_{hex(id(chart))[2:8]}"
                requests.append({
                    'createImage': {
                        'objectId': object_id,
                        'url': chart_urls[chart_id],
                        'elementProperties': {
                            'pageObjectId': self.id,
                            'size': {
                                'height': {'magnitude': height_pt, 'unit': 'PT'},
                                'width': {'magnitude': width_pt, 'unit': 'PT'},
                            },
                            'transform': {
                                'translateX': x_pt,
                                'translateY': y_pt,
                                'scaleX': 1,
                                'scaleY': 1,
                                'unit': 'PT'
                            }
                        }
                    }
                })
        
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
            slide_id = self.id,
            charts_count = len(self.charts),
            replacements_count = len(self.replacements),
            chart_images = [chart.title or f"Chart {i+1}" for i, chart in enumerate(self.charts)]
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
    
    model_config = ConfigDict(extra = "forbid", arbitrary_types_allowed = True)
    
    name: Annotated[str, Field(..., description = "Presentation name")]
    slides: Annotated[List[Slide], Field(..., description = "List of slides in the presentation")]
    provider: Annotated[PresentationProvider, Field(..., exclude = True, description = "Presentation provider instance")]
    
    def render(self) -> PresentationResult:
        """Render the complete presentation with all content and styling.
        
        Executes the full presentation rendering pipeline including presentation
        creation, data prefetching, chart generation, text replacements, and
        optional sharing. The process is optimized for performance using concurrent
        operations where possible.
        
        The rendering process follows these steps:
        1. Create a new presentation using the configured provider
        2. Prefetch all data sources concurrently to populate caches
        3. Process each slide sequentially to maintain order
        4. Generate and upload charts with positioning calculations
        5. Execute text replacements with comprehensive error handling
        6. Share the presentation if configured
        
        Returns:
            PresentationResult containing the presentation URL, operation counts,
            performance metrics, and timestamp information for monitoring and
            user feedback purposes.
            
        Raises:
            RenderingError: If presentation creation fails or critical operations fail.
            AuthenticationError: If provider authentication fails.
            DataError: If required data sources are unavailable or invalid.
            
        Example:
            >>> presentation = Presentation(
            ...     name="Monthly Report",
            ...     slides=slides,
            ...     provider=provider
            ... )
            >>> 
            >>> try:
            ...     result = presentation.render()
            ...     print(f"✓ Presentation created: {result.presentation_url}")
            ...     print(f"✓ Generated {result.charts_generated} charts")
            ...     print(f"✓ Made {result.replacements_made} text replacements")
            ...     print(f"✓ Completed in {result.render_time:.1f} seconds")
            ... except RenderingError as e:
            ...     print(f"✗ Rendering failed: {e}")
        """
        logger = get_logger(__name__)
        start_time = time.time()

        presentation_id = self.provider.create_presentation(self.name)
        
        # Pre-fetch all data sources (uses caching)
        self._prefetch_data_sources()

        total_charts = 0
        total_replacements = 0
        
        for slide in self.slides:
            # Generate charts for this slide
            for chart in slide.charts:
                try:
                    if chart.data_source:
                        df = chart.data_source.fetch_data()
                        if chart.data_transforms:
                            df = apply_data_transforms(chart.data_transforms, df)

                    image_data = chart.generate_chart_image(df)

                    image_url, _ = self.provider.upload_chart_image(
                        presentation_id, image_data, f"chart_{chart.title or 'untitled'}.png"
                    )

                    x_pt, y_pt, width_pt, height_pt = compute_chart_dimensions(
                        x=chart.x,
                        y=chart.y,
                        width=chart.width,
                        height=chart.height,
                        dimensions_format=chart.dimensions_format,
                        alignment_format=chart.alignment_format,
                    )

                    self.provider.insert_chart_to_slide(
                        presentation_id, slide.id, image_url,
                        x_pt, y_pt, width_pt, height_pt
                    )
                    total_charts += 1
                except Exception as e:
                    logger.error(f"Failed to process chart on slide '{slide.id}'.")
                    try:
                        x_pt, y_pt, width_pt, height_pt = compute_chart_dimensions(
                            x=chart.x,
                            y=chart.y,
                            width=chart.width,
                            height=chart.height,
                            dimensions_format=chart.dimensions_format,
                            alignment_format=chart.alignment_format,
                        )
                        
                        error_image_url = "https://drive.google.com/uc?id=10geCrUpKZmQBesbhjtepZ9NexE-HRkn4"
                        self.provider.insert_chart_to_slide(
                            presentation_id,
                            slide.id,
                            error_image_url,
                            x=x_pt,
                            y=y_pt,
                            width=width_pt,
                            height=height_pt,
                        )
                        logger.info(f"Inserted error placeholder for chart on slide '{slide.id}'")
                    except Exception as img_e:
                        logger.error(f"Failed to insert error placeholder for chart on slide '{slide.id}': {img_e}")
                    continue
            
            # Process replacements for this slide
            for replacement in slide.replacements:
                try:
                    replacement_result = replacement.get_replacement()
                    
                    # Handle different replacement types
                    if hasattr(replacement, 'placeholder'):
                        # Text and AI text replacements
                        replacements_made = self.provider.replace_text_in_slide(
                            presentation_id, slide.id, 
                            replacement.placeholder, str(replacement_result)
                        )
                        total_replacements += replacements_made
                        logger.debug(f"Processed replacement for {replacement.placeholder}: {replacements_made} occurrences")
                    elif hasattr(replacement, 'prefix'):
                        # Table replacements return a dictionary of placeholder->value
                        if isinstance(replacement_result, dict):
                            for placeholder, value in replacement_result.items():
                                time.sleep(1)
                                replacements_made = self.provider.replace_text_in_slide(
                                    presentation_id, slide.id, 
                                    placeholder, str(value)
                                )
                                total_replacements += replacements_made
                                logger.debug(f"Processed table replacement for {placeholder}: {replacements_made} occurrences")
                except Exception as e:
                    replacement_type = getattr(replacement, 'type', type(replacement).__name__)
                    placeholder = getattr(replacement, 'placeholder', 'unknown')
                    logger.error(f"Failed to process {replacement_type} replacement '{placeholder}': {e}")
                    # Continue with other replacements rather than failing entirely
                    continue
        
        # Share presentation if configured
        if hasattr(self.provider, 'config') and hasattr(self.provider.config, 'share_with'):
            if self.provider.config.share_with:
                self.provider.share_presentation(
                    presentation_id, 
                    self.provider.config.share_with,
                    getattr(self.provider.config, 'share_role', 'writer')
                )

        render_time = time.time() - start_time
        
        return PresentationResult(
            presentation_id = presentation_id,
            presentation_url = self.provider.get_presentation_url(presentation_id),
            charts_generated = total_charts,
            replacements_made = total_replacements,
            render_time = render_time
        )
    
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
        task_func: callable,
        task_name: str,
        max_workers: int = 10,
        collect_results: bool = False
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
        
        results = [] if collect_results else None
        
        logger.info(f"Executing {len(items)} {task_name} tasks concurrently")
        
        with ThreadPoolExecutor(max_workers=min(len(items), max_workers)) as executor:
            # Submit all tasks
            future_to_item = {
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
                if hasattr(replacement, 'data_source') and replacement.data_source:
                    source_key = (replacement.data_source.type, replacement.data_source.name)
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        unique_sources.append((replacement.data_source.name, replacement.data_source))

            for chart in slide.charts:
                if hasattr(chart, 'data_source') and chart.data_source:
                    source_key = (chart.data_source.type, chart.data_source.name)
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        unique_sources.append((chart.data_source.name, chart.data_source))

        self._execute_concurrent_tasks(
            items = unique_sources,
            task_func = lambda source: source.fetch_data(),
            task_name = "data source fetch",
            max_workers = 10,
            collect_results = False
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
        if not self.google_slides_service:
            raise RenderingError("Google Slides service is required for chart generation")
        
        chart_urls = {}
        file_ids = []
        
        for slide in self.slides:
            for i, chart in enumerate(slide.charts):
                # Generate public URL and file ID for chart
                public_url, file_id = chart.generate_public_url(
                    self.google_slides_service.drive_service
                )
                chart_id = f"chart_{i}_{id(chart)}"
                chart_urls[chart_id] = public_url
                file_ids.append(file_id)
        
        return chart_urls, file_ids
