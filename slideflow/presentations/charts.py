import io
import re
import uuid
import pandas as pd
import plotly.io as pio
import plotly.graph_objects as go
from abc import ABC, abstractmethod
from googleapiclient.http import MediaIoBaseUpload
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict, Any, Optional, Callable, Union, Annotated, Literal, Tuple

from slideflow.presentations.positioning import safe_eval_expression
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.data.connectors.base import BaseSourceConfig as DataSourceConfig
from slideflow.utilities.exceptions import ChartGenerationError
from slideflow.constants import GoogleSlides, FileExtensions
from slideflow.builtins.template_engine import get_template_engine

class BaseChart(BaseModel, ABC):
    """Base class for all chart types."""
    
    model_config = ConfigDict(extra = "forbid", arbitrary_types_allowed = True)
    
    type: Annotated[str, Field(..., description = "Chart type discriminator")]
    title: Annotated[Optional[str], Field(None, description = "Chart title")]
    data_source: Annotated[Optional[DataSourceConfig], Field(None, description = "Data source configuration")]
    data_transforms: Annotated[Optional[List[Dict[str, Any]]], Field(None, description = "Optional data transformations (resolved by ConfigLoader)")]
    
    # Chart positioning and sizing (supports expressions and different units)
    width: Annotated[Union[float, str], Field(400, description = "Chart width (supports expressions like '400 + 50')")]
    height: Annotated[Union[float, str], Field(300, description = "Chart height (supports expressions)")]
    x: Annotated[Union[float, str], Field(50, description = "X position (supports expressions)")]
    y: Annotated[Union[float, str], Field(50, description = "Y position (supports expressions)")]
    dimensions_format: Annotated[str, Field("pt", description = "Dimension format: 'pt', 'emu', 'relative', or 'expression'")]
    alignment_format: Annotated[Optional[str], Field(None, description = "Alignment format like 'center-top', 'left-bottom'")]
    
    @field_validator("dimensions_format")
    @classmethod
    def validate_dimensions_format(cls, v: str) -> str:
        """Validate dimensions_format is supported."""
        if v not in ("pt", "emu", "relative", "expression"):
            raise ChartGenerationError(f"dimensions_format must be 'pt', 'emu', 'relative', or 'expression', got: {v}")
        return v
    
    @field_validator("alignment_format")
    @classmethod
    def validate_alignment_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate alignment_format has correct format."""
        if v is None:
            return v
        
        if '-' not in v:
            raise ChartGenerationError(f"alignment_format must be 'horizontal-vertical', got: {v}")
        
        horizontal, vertical = v.split('-')
        if horizontal not in ("left", "center", "right"):
            raise ChartGenerationError(f"horizontal alignment must be 'left', 'center', or 'right', got: {horizontal}")
        if vertical not in ("top", "center", "bottom"):
            raise ChartGenerationError(f"vertical alignment must be 'top', 'center', or 'bottom', got: {vertical}")
        
        return v
    
    def fetch_data(self) -> Optional[pd.DataFrame]:
        """Uniform data fetching like replacements.
        
        Returns:
            DataFrame if data source is configured, None otherwise
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None
    
    def apply_data_transforms(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply data transformations using the shared function."""
        return apply_data_transforms(self.data_transforms, df)
    
    @abstractmethod
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate chart image from data.
        
        Each chart type implements its own visualization logic.
        
        Args:
            df: DataFrame with the data
            
        Returns:
            Image bytes in PNG format
        """
        ...
    
    def generate_public_url(self, drive_service) -> Tuple[str, str]:
        """Standard chart generation pipeline.
        
        1. Fetch data (with caching) or use static data
        2. Generate chart image using chart-specific logic
        3. Upload to Google Drive
        4. Return public URL and file ID
        
        Args:
            drive_service: Google Drive service instance
            
        Returns:
            Tuple of (public_url, file_id) for the chart image
        """
        df = self.fetch_data()
        if df is None:
            # For charts without data sources, create empty DataFrame
            # Chart implementation should handle static data in traces
            df = pd.DataFrame()

        image_bytes = self.generate_chart_image(df)

        return self._upload_to_drive(image_bytes, drive_service)
    
    def _upload_to_drive(self, image_bytes: bytes, drive_service) -> Tuple[str, str]:
        """Upload image bytes to Google Drive and return public URL and file ID.
        
        Args:
            image_bytes: PNG image data
            drive_service: Google Drive service instance
            
        Returns:
            Tuple of (public_url, file_id) for accessing and later deleting the image
        """

        file_metadata = {
            'name': f'{self.title or "chart"}_{uuid.uuid4().hex[:8]}{FileExtensions.PNG}'
        }

        media = MediaIoBaseUpload(
            io.BytesIO(image_bytes),
            mimetype = 'image/png',
            resumable = True
        )
        
        uploaded_file = drive_service.files().create(
            body = file_metadata,
            media_body = media
        ).execute()
        
        file_id = uploaded_file['id']
        
        # Make publicly viewable
        drive_service.permissions().create(
            fileId = file_id,
            body = {'role': 'reader', 'type': 'anyone'}
        ).execute()

        public_url = f"https://drive.google.com/uc?id={file_id}"
        return public_url, file_id

class PlotlyGraphObjects(BaseChart):
    """Advanced Plotly chart using graph_objects for complex visualizations."""
    
    type: Literal["plotly_go"] = "plotly_go"
    traces: Annotated[List[Dict[str, Any]], Field(..., description = "List of trace configurations")]
    layout_config: Annotated[Optional[Dict[str, Any]], Field(None, description = "Plotly layout configuration")]
    
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate chart using Plotly graph objects.
        
        Args:
            df: DataFrame with the data
            
        Returns:
            PNG image bytes
        """
        transformed_df = self.apply_data_transforms(df)
        
        fig = go.Figure()

        for trace_config in self.traces:
            trace_config_copy = trace_config.copy()
            trace_type = trace_config_copy.pop('type')  # e.g., 'scatter', 'bar'
            trace_class = getattr(go, trace_type.title())  # go.Scatter, go.Bar
            
            # Replace column references with actual data
            processed_config = self._process_trace_config(trace_config_copy, transformed_df)
            
            fig.add_trace(trace_class(**processed_config))
        
        # Apply layout
        if self.layout_config:
            fig.update_layout(**self.layout_config)
        
        if self.title and (not self.layout_config or 'title' not in self.layout_config):
            fig.update_layout(title = self.title)
        
        # Evaluate width and height if they are expressions
        chart_width = safe_eval_expression(self.width) if isinstance(self.width, str) else self.width
        chart_height = safe_eval_expression(self.height) if isinstance(self.height, str) else self.height
        
        # Convert from points (72 DPI) to pixels (96 DPI) for Plotly
        # Google Slides uses points as its unit (72 DPI), but Plotly's to_image expects pixels at 96 DPI
        # Conversion factor ensures the chart appears at the correct size in slides
        POINTS_TO_PIXELS = GoogleSlides.POINTS_TO_PIXELS_RATIO
        image_width = int(chart_width * POINTS_TO_PIXELS)
        image_height = int(chart_height * POINTS_TO_PIXELS)
        
        return pio.to_image(fig, format = 'png', engine = 'auto', width = image_width, height = image_height)
    
    def _process_trace_config(self, config: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        """Replace column references with actual data.
        
        Args:
            config: Trace configuration with potential column references
            df: DataFrame containing the data (may be empty for static charts)
            
        Returns:
            Processed configuration with actual data
        """
        processed = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith('$') and not '%{' in value:
                # Column reference: "$column_name" -> df['column_name']
                # But not Plotly template strings like "$%{y:,.0f}"
                column_name = value[1:]
                if not df.empty and column_name in df.columns:
                    processed[key] = df[column_name].tolist()
                elif df.empty:
                    # For static charts without data, skip column references
                    # They should provide static data directly in the config
                    continue
                else:
                    available_columns = list(df.columns) if not df.empty else []
                    raise ChartGenerationError(
                        f"Column '{column_name}' not found in PlotlyGraphObjects trace config. "
                        f"Available columns: {available_columns}. "
                        f"DataFrame shape: {df.shape}"
                    )
            elif isinstance(value, dict):
                # Recursively process nested dictionaries
                processed[key] = self._process_trace_config(value, df)
            elif isinstance(value, list):
                # Process lists that might contain column references
                # Column references are $word (alphanumeric/underscore), including complex names like $_color_col_0
                column_ref_pattern = re.compile(r'^\$([a-zA-Z_]\w*)$')
                processed_list = []
                
                for item in value:
                    if isinstance(item, str):
                        match = column_ref_pattern.match(item)
                        if match and not df.empty and match.group(1) in df.columns:
                            # Valid column reference
                            processed_list.append(df[match.group(1)].tolist())
                        else:
                            # Not a column reference or column doesn't exist
                            processed_list.append(item)
                    else:
                        processed_list.append(item)
                        
                processed[key] = processed_list
            else:
                processed[key] = value
        return processed

class CustomChart(BaseChart):
    """Custom chart using user-defined functions."""
    
    type: Literal["custom"] = "custom"
    chart_fn: Annotated[Callable, Field(..., description = "Chart function resolved by ConfigLoader")]
    chart_config: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Configuration for the custom function")]
    
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate chart using custom function.
        
        Args:
            df: DataFrame with the data
            
        Returns:
            PNG image bytes
        """
        transformed_df = self.apply_data_transforms(df)

        chart_func = self.chart_fn

        processed_config = self._process_config(self.chart_config, transformed_df)

        processed_config['title'] = self.title

        return chart_func(transformed_df, processed_config, self)
    
    def _process_config(self, config: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        """Replace column references with actual data.
        
        Args:
            config: Configuration with potential column references
            df: DataFrame containing the data
            
        Returns:
            Processed configuration
        """
        processed = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith('$'):
                column_name = value[1:]
                if column_name in df.columns:
                    processed[key] = df[column_name]
                else:
                    available_columns = list(df.columns) if not df.empty else []
                    raise ChartGenerationError(
                        f"Column '{column_name}' not found in CustomChart config. "
                        f"Available columns: {available_columns}. "
                        f"DataFrame shape: {df.shape}"
                    )
            elif isinstance(value, list):
                # Handle lists that might contain column references
                processed[key] = [
                    df[item[1:]] if isinstance(item, str) and item.startswith('$') and item[1:] in df.columns
                    else item for item in value
                ]
            elif isinstance(value, dict):
                # Recursively process nested dictionaries
                processed[key] = self._process_config(value, df)
            else:
                processed[key] = value
        return processed

class TemplateChart(BaseChart):
    """Chart generated from YAML template."""
    
    type: Literal["template"] = "template"
    template_name: Annotated[str, Field(..., description="Name of the YAML template to use")]
    template_config: Annotated[Dict[str, Any], Field(default_factory=dict, description="Configuration for the template")]
    
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate chart using YAML template."""
        
        # Get the template engine
        engine = get_template_engine()
        
        # Render the template with user config
        rendered_config = engine.render_template(self.template_name, self.template_config)
        
        # Create a PlotlyGraphObjects chart with the rendered config
        # Combine user transforms with template transforms
        all_transforms = (self.data_transforms or []) + (rendered_config.get('data_transforms', []))
        
        plotly_chart = PlotlyGraphObjects(
            type="plotly_go",
            data_source=None,  # We already have the data
            data_transforms=all_transforms,
            traces=rendered_config['traces'],
            layout_config=rendered_config.get('layout_config', {}),
            width=self.width,
            height=self.height,
            x=self.x,
            y=self.y,
            dimensions_format=self.dimensions_format
        )
        
        # Generate the image using the plotly chart's method
        return plotly_chart.generate_chart_image(df)


# Chart Union for discriminator
ChartUnion = Annotated[
    Union[PlotlyGraphObjects, CustomChart, TemplateChart],
    Field(discriminator = "type")
]
