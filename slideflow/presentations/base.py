"""Base classes for presentations and slides using modern Pydantic patterns."""
import time
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Annotated, Tuple

from slideflow.presentations.positioning import compute_chart_dimensions
from slideflow.replacements.base import BaseReplacement
from slideflow.utilities.exceptions import RenderingError
from slideflow.presentations.providers.base import PresentationProvider
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.utilities.logging import get_logger


class PresentationResult(BaseModel):
    """Results from complete presentation rendering."""
    
    model_config = ConfigDict(extra = "forbid")
    
    presentation_id: Annotated[str, Field(..., description = "Google Slides presentation ID")]
    presentation_url: Annotated[str, Field(..., description = "URL to access the presentation")]
    charts_generated: Annotated[int, Field(..., description = "Number of charts successfully generated")]
    replacements_made: Annotated[int, Field(..., description = "Number of text replacements made")]
    render_time: Annotated[float, Field(..., description = "Time taken to render presentation in seconds")]
    created_at: Annotated[datetime, Field(default_factory = datetime.now, description = "Timestamp when presentation was created")]


class SlideResult(BaseModel):
    """Results from individual slide rendering."""
    
    model_config = ConfigDict(extra = "forbid")
    
    slide_id: Annotated[str, Field(..., description = "Slide ID")]
    charts_count: Annotated[int, Field(..., description = "Number of charts on this slide")]
    replacements_count: Annotated[int, Field(..., description = "Number of replacements on this slide")]
    chart_images: Annotated[List[str], Field(..., description = "List of chart titles")]


class Slide(BaseModel):
    """Individual slide with content."""
    
    model_config = ConfigDict(extra = "forbid", arbitrary_types_allowed = True)
    
    id: Annotated[str, Field(..., description = "Slide ID in Google Slides")]
    title: Annotated[Optional[str], Field(None, description = "Slide title for documentation")]
    replacements: Annotated[List[BaseReplacement], Field(default_factory = list, description = "Text replacements for this slide")]
    charts: Annotated[List["BaseChart"], Field(default_factory = list, description = "Charts to generate for this slide")]
    
    def build_update_requests(self, chart_urls: Dict[str, str]) -> List[Dict[str, Any]]:
        """Build Google Slides API requests for this slide.
        
        Args:
            chart_urls: Mapping of chart IDs to public URLs
            
        Returns:
            List of Google Slides API request objects
        """
        requests = []
        
        # Build text replacement requests
        for replacement in self.replacements:
            replacement_result = replacement.get_replacement()
            
            # Handle different replacement types
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
                    x=chart.x,
                    y=chart.y,
                    width=chart.width,
                    height=chart.height,
                    dimensions_format=chart.dimensions_format,
                    alignment_format=chart.alignment_format,
                    slides_app=None,  # TODO: Get slide dimensions from template
                    page_width_pt=720,  # Standard Google Slides width in points
                    page_height_pt=540  # Standard Google Slides height in points
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
        """Get rendering result for this slide."""
        return SlideResult(
            slide_id=self.id,
            charts_count=len(self.charts),
            replacements_count=len(self.replacements),
            chart_images=[chart.title or f"Chart {i+1}" for i, chart in enumerate(self.charts)]
        )


class Presentation(BaseModel):
    """Main presentation container."""
    
    model_config = ConfigDict(extra = "forbid", arbitrary_types_allowed = True)
    
    name: Annotated[str, Field(..., description = "Presentation name")]
    slides: Annotated[List[Slide], Field(..., description = "List of slides in the presentation")]
    provider: Annotated[PresentationProvider, Field(..., exclude=True, description = "Presentation provider instance")]
    
    def render(self) -> PresentationResult:
        """Render entire presentation.
        
        Returns:
            PresentationResult with presentation details
        """
        logger = get_logger(__name__)
        start_time = time.time()
        
        # Create presentation using provider
        presentation_id = self.provider.create_presentation(self.name)
        
        # Pre-fetch all data sources (uses caching)
        self._prefetch_data_sources()
        
        # Generate and process all slides
        total_charts = 0
        total_replacements = 0
        
        for slide in self.slides:
            # Generate charts for this slide
            for chart in slide.charts:
                if chart.data_source:
                    df = chart.data_source.fetch_data()
                    if chart.data_transforms:
                        df = apply_data_transforms(chart.data_transforms, df)
                    
                    # Generate chart image
                    image_data = chart.generate_chart_image(df)
                    
                    # Upload chart image
                    image_url, _ = self.provider.upload_chart_image(
                        presentation_id, image_data, f"chart_{chart.title or 'untitled'}.png"
                    )
                    
                    # Insert chart into slide  
                    self.provider.insert_chart_to_slide(
                        presentation_id, slide.id, image_url,
                        chart.x, chart.y, chart.width, chart.height
                    )
                    total_charts += 1
            
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
        
        # Calculate results
        render_time = time.time() - start_time
        
        return PresentationResult(
            presentation_id=presentation_id,
            presentation_url=self.provider.get_presentation_url(presentation_id),
            charts_generated=total_charts,
            replacements_made=total_replacements,
            render_time=render_time
        )
    
    def get_slide(self, slide_id: str) -> Optional[Slide]:
        """Get slide by ID.
        
        Args:
            slide_id: The slide identifier
            
        Returns:
            Slide object if found, None otherwise
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
        """Execute tasks concurrently with proper error handling.
        
        Args:
            items: List of (identifier, item) tuples to process
            task_func: Function to call for each item
            task_name: Name for logging purposes
            max_workers: Maximum number of concurrent workers
            collect_results: Whether to collect and return results
            
        Returns:
            List of results if collect_results=True, empty list otherwise
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
        """Pre-fetch all data sources to populate cache using concurrent execution."""
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
            
            # Collect from charts
            for chart in slide.charts:
                if hasattr(chart, 'data_source') and chart.data_source:
                    source_key = (chart.data_source.type, chart.data_source.name)
                    if source_key not in seen_sources:
                        seen_sources.add(source_key)
                        unique_sources.append((chart.data_source.name, chart.data_source))
        
        
        # Execute concurrent data fetching
        self._execute_concurrent_tasks(
            items=unique_sources,
            task_func=lambda source: source.fetch_data(),
            task_name="data source fetch",
            max_workers=10,
            collect_results=False
        )
    
    def _generate_and_upload_charts(self) -> Tuple[Dict[str, str], List[str]]:
        """Generate all charts and upload to Google Drive.
        
        Returns:
            Tuple of (chart_urls_dict, file_ids_list) for cleanup
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
