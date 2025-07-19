"""Chart generation system for creating data visualizations in presentations.

This module provides a comprehensive chart generation framework for Slideflow
presentations, supporting multiple chart types and rendering backends. The system
is designed to be extensible, allowing for custom chart types and integrations
with various visualization libraries.

The chart system includes:
    - Base chart class with common functionality for all chart types
    - Plotly-based charts using the graph_objects API for advanced visualizations
    - Custom chart support for user-defined visualization functions
    - Template-based charts for reusable chart configurations
    - Integration with data sources and transformations
    - Automatic image generation and upload to presentation platforms

Architecture:
    All charts inherit from BaseChart and implement the generate_chart_image method.
    Charts can fetch data from configured data sources, apply transformations, and
    generate images that are automatically uploaded to the presentation platform.

Key Features:
    - Flexible positioning with expression support
    - Data transformation pipeline integration
    - Automatic caching of data sources
    - Support for static and dynamic data
    - Type-safe configuration with Pydantic
    - Extensible chart type system

Example:
    Creating a line chart with data transformation:
    
    >>> from slideflow.presentations.charts import PlotlyGraphObjects
    >>> from slideflow.data.connectors import CSVDataSource
    >>> 
    >>> chart = PlotlyGraphObjects(
    ...     type="plotly_go",
    ...     title="Monthly Revenue",
    ...     data_source=CSVDataSource(name="revenue", file_path="data/revenue.csv"),
    ...     data_transforms=[{"type": "filter", "column": "year", "value": 2024}],
    ...     traces=[{
    ...         "type": "scatter",
    ...         "x": "$month",
    ...         "y": "$revenue",
    ...         "mode": "lines+markers",
    ...         "name": "Revenue Trend"
    ...     }],
    ...     x=100, y=150, width=500, height=400
    ... )
    >>> 
    >>> # Generate and upload chart
    >>> url, file_id = chart.generate_public_url(drive_service)
"""

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

from slideflow.constants import GoogleSlides, FileExtensions
from slideflow.utilities.exceptions import ChartGenerationError
from slideflow.builtins.template_engine import get_template_engine
from slideflow.presentations.positioning import safe_eval_expression
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.data.connectors.base import BaseSourceConfig as DataSourceConfig

class BaseChart(BaseModel, ABC):
    """Abstract base class for all chart types in Slideflow.
    
    This class provides the common interface and functionality for all chart
    implementations. It handles data fetching, transformation, positioning,
    and the overall chart generation pipeline. Concrete chart types must
    implement the generate_chart_image method to create their specific
    visualizations.
    
    The base class integrates with:
    - Data sources for fetching chart data
    - Data transformation pipeline for preprocessing
    - Positioning system with expression support
    - Google Drive for image upload and sharing
    
    Attributes:
        type: Chart type identifier used for discriminated unions.
        title: Optional title for the chart, used in image naming.
        data_source: Optional data source configuration for dynamic data.
        data_transforms: List of data transformation operations to apply.
        width: Chart width in specified units (supports expressions).
        height: Chart height in specified units (supports expressions).
        x: Horizontal position (supports expressions).
        y: Vertical position (supports expressions).
        dimensions_format: Unit format for dimensions ('pt', 'emu', 'relative', 'expression').
        alignment_format: Optional alignment specification like 'center-top'.
        
    Example:
        Subclassing BaseChart for a custom chart type:
        
        >>> class MyChart(BaseChart):
        ...     type: Literal["my_chart"] = "my_chart"
        ...     
        ...     def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        ...         # Custom visualization logic here
        ...         fig = create_my_visualization(df)
        ...         return fig.to_png()
    """
    
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
        """Validate that dimensions_format uses a supported unit system.
        
        Ensures the dimensions format is one of the supported types for
        consistent positioning and sizing across different presentation platforms.
        
        Args:
            v: The dimensions format string to validate.
            
        Returns:
            The validated dimensions format string.
            
        Raises:
            ChartGenerationError: If the format is not supported.
            
        Example:
            >>> BaseChart.validate_dimensions_format("pt")  # Valid
            >>> BaseChart.validate_dimensions_format("pixels")  # Raises error
        """
        if v not in ("pt", "emu", "relative", "expression"):
            raise ChartGenerationError(f"dimensions_format must be 'pt', 'emu', 'relative', or 'expression', got: {v}")
        return v
    
    @field_validator("alignment_format")
    @classmethod
    def validate_alignment_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate that alignment_format follows the expected pattern.
        
        Ensures alignment format follows the 'horizontal-vertical' pattern
        with valid alignment values for each dimension.
        
        Args:
            v: The alignment format string to validate, or None.
            
        Returns:
            The validated alignment format string, or None if not provided.
            
        Raises:
            ChartGenerationError: If the format doesn't match expected pattern
                or contains invalid alignment values.
                
        Example:
            >>> BaseChart.validate_alignment_format("center-top")  # Valid
            >>> BaseChart.validate_alignment_format("middle-top")  # Raises error
        """
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
        """Fetch data from the configured data source if available.
        
        Provides a uniform interface for data fetching across all chart types.
        If a data source is configured, it fetches the data (potentially from
        cache). If no data source is configured, returns None, indicating the
        chart should use static data.
        
        Returns:
            DataFrame containing the fetched data if data_source is configured,
            None if no data source is set (chart should use static data).
            
        Example:
            >>> chart = MyChart(data_source=csv_source)
            >>> df = chart.fetch_data()
            >>> if df is not None:
            ...     print(f"Fetched {len(df)} rows of data")
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None
    
    def apply_data_transforms(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply configured data transformations to the DataFrame.
        
        Delegates to the shared data transformation function to apply any
        configured transformations like filtering, aggregation, or calculations.
        
        Args:
            df: Input DataFrame to transform.
            
        Returns:
            Transformed DataFrame with all operations applied.
            
        Example:
            >>> chart = MyChart(data_transforms=[{
            ...     "type": "filter",
            ...     "column": "region",
            ...     "value": "North America"
            ... }])
            >>> transformed_df = chart.apply_data_transforms(original_df)
        """
        return apply_data_transforms(self.data_transforms, df)
    
    @abstractmethod
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate a chart image from the provided data.
        
        This is the core method that each chart type must implement to create
        its specific visualization. The method should handle both cases where
        df contains data from a data source and where df is empty (for static
        charts that define their data inline).
        
        Implementations should:
        1. Apply any data transformations using apply_data_transforms
        2. Create the visualization using the chart library
        3. Apply positioning and sizing based on width/height attributes
        4. Return the image as PNG bytes
        
        Args:
            df: DataFrame containing the chart data. May be empty for static
                charts that define data directly in their configuration.
                
        Returns:
            PNG image data as bytes, ready for upload to the presentation platform.
            
        Raises:
            ChartGenerationError: If chart generation fails due to invalid
                configuration or data issues.
                
        Example:
            Implementation for a simple bar chart:
            
            >>> def generate_chart_image(self, df: pd.DataFrame) -> bytes:
            ...     transformed_df = self.apply_data_transforms(df)
            ...     fig = create_bar_chart(transformed_df, self.config)
            ...     return fig.to_png(width=self.width, height=self.height)
        """
        ...
    
    def generate_public_url(self, drive_service) -> Tuple[str, str]:
        """Execute the complete chart generation and upload pipeline.
        
        This method orchestrates the entire process of creating a chart and
        making it available for insertion into a presentation:
        
        1. Fetch data from the configured source (with caching)
        2. Generate the chart image using the concrete implementation
        3. Upload the image to Google Drive
        4. Make the image publicly accessible
        5. Return the public URL and file ID
        
        The method handles both dynamic charts (with data sources) and static
        charts (with data defined in configuration).
        
        Args:
            drive_service: Authenticated Google Drive service instance for
                uploading the generated chart image.
                
        Returns:
            Tuple containing:
            - public_url: Publicly accessible URL for the chart image
            - file_id: Google Drive file ID for later cleanup operations
            
        Raises:
            ChartGenerationError: If chart generation fails.
            UploadError: If uploading to Google Drive fails.
            
        Example:
            >>> chart = PlotlyGraphObjects(type="plotly_go", traces=[...])
            >>> url, file_id = chart.generate_public_url(drive_service)
            >>> print(f"Chart available at: {url}")
        """
        df = self.fetch_data()
        if df is None:
            # For charts without data sources, create empty DataFrame
            # Chart implementation should handle static data in traces
            df = pd.DataFrame()

        image_bytes = self.generate_chart_image(df)

        return self._upload_to_drive(image_bytes, drive_service)
    
    def _upload_to_drive(self, image_bytes: bytes, drive_service) -> Tuple[str, str]:
        """Upload chart image to Google Drive and make it publicly accessible.
        
        Handles the upload process including file naming, permission setting,
        and public URL generation. The uploaded file is made publicly readable
        so it can be embedded in presentations.
        
        Args:
            image_bytes: PNG image data generated by the chart.
            drive_service: Authenticated Google Drive API service instance.
            
        Returns:
            Tuple containing:
            - public_url: Direct link URL for embedding the image
            - file_id: Google Drive file identifier for management
            
        Raises:
            HttpError: If the Drive API requests fail.
            
        Example:
            >>> image_data = chart.generate_chart_image(df)
            >>> url, file_id = chart._upload_to_drive(image_data, drive_service)
            >>> # Image is now accessible at url and can be deleted using file_id
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
    """Advanced chart implementation using Plotly's graph_objects API.
    
    This chart type provides access to the full power of Plotly's graph_objects
    library, enabling complex, interactive visualizations including multi-trace
    charts, advanced layouts, and custom styling. It supports all Plotly trace
    types like scatter, bar, heatmap, 3D plots, and more.
    
    The chart configuration uses a declarative approach where traces and layout
    are defined in the configuration. Column references in the format '$column_name'
    are automatically replaced with data from the DataFrame.
    
    Attributes:
        type: Always "plotly_go" for this chart type.
        traces: List of Plotly trace configurations, each specifying a data series.
        layout_config: Optional Plotly layout configuration for styling and formatting.
        
    Example:
        Creating a multi-trace line chart:
        
        >>> chart = PlotlyGraphObjects(
        ...     type="plotly_go",
        ...     title="Sales Comparison",
        ...     data_source=sales_data_source,
        ...     traces=[
        ...         {
        ...             "type": "scatter",
        ...             "x": "$month",
        ...             "y": "$product_a_sales",
        ...             "mode": "lines+markers",
        ...             "name": "Product A"
        ...         },
        ...         {
        ...             "type": "scatter",
        ...             "x": "$month",
        ...             "y": "$product_b_sales",
        ...             "mode": "lines+markers",
        ...             "name": "Product B"
        ...         }
        ...     ],
        ...     layout_config={
        ...         "xaxis": {"title": "Month"},
        ...         "yaxis": {"title": "Sales ($)"},
        ...         "hovermode": "x unified"
        ...     }
        ... )
        
        Creating a static chart without data source:
        
        >>> static_chart = PlotlyGraphObjects(
        ...     type="plotly_go",
        ...     traces=[{
        ...         "type": "pie",
        ...         "values": [30, 25, 20, 15, 10],
        ...         "labels": ["A", "B", "C", "D", "E"]
        ...     }]
        ... )
    """
    
    type: Literal["plotly_go"] = "plotly_go"
    traces: Annotated[List[Dict[str, Any]], Field(..., description = "List of trace configurations")]
    layout_config: Annotated[Optional[Dict[str, Any]], Field(None, description = "Plotly layout configuration")]
    
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate a chart image using Plotly graph objects.
        
        Creates a Plotly figure by processing trace configurations, replacing
        column references with actual data, and applying layout settings. The
        method handles both dynamic data from DataFrames and static data defined
        directly in trace configurations.
        
        The image dimensions are converted from points (used by Google Slides)
        to pixels (used by Plotly) to ensure correct sizing in presentations.
        
        Args:
            df: DataFrame containing the chart data. May be empty for static
                charts that define data directly in trace configurations.
                
        Returns:
            PNG image bytes of the generated chart, ready for upload.
            
        Raises:
            ChartGenerationError: If column references are invalid or chart
                generation fails.
                
        Example:
            >>> df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
            >>> image_bytes = chart.generate_chart_image(df)
            >>> with open("chart.png", "wb") as f:
            ...     f.write(image_bytes)
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
        """Process trace configuration by replacing column references with data.
        
        Recursively processes the trace configuration dictionary, replacing any
        column references (strings starting with '$') with actual data from the
        DataFrame. Handles nested dictionaries and lists, preserving the structure
        while substituting data values.
        
        Special handling for:
        - Column references: "$column_name" -> df['column_name'].tolist()
        - Plotly template strings: Preserved as-is (e.g., "$%{y:,.0f}")
        - Nested structures: Recursively processed
        - Static data: Passed through unchanged
        
        Args:
            config: Trace configuration dictionary that may contain column
                references in the format '$column_name'.
            df: DataFrame containing the data columns. May be empty for static
                charts, in which case column references are skipped.
                
        Returns:
            Processed configuration with column references replaced by actual
            data arrays, ready for use in Plotly trace construction.
            
        Raises:
            ChartGenerationError: If a referenced column doesn't exist in the
                DataFrame (unless DataFrame is empty).
                
        Example:
            >>> config = {"x": "$months", "y": "$revenue", "name": "Revenue"}
            >>> df = pd.DataFrame({"months": ["Jan", "Feb"], "revenue": [100, 150]})
            >>> processed = chart._process_trace_config(config, df)
            >>> # processed = {"x": ["Jan", "Feb"], "y": [100, 150], "name": "Revenue"}
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
    """Chart type that uses custom user-defined visualization functions.
    
    This chart type allows users to provide their own chart generation functions,
    enabling complete flexibility in visualization creation. The custom function
    receives the DataFrame, configuration, and chart instance, and must return
    PNG image bytes.
    
    Custom functions can use any visualization library (matplotlib, seaborn,
    plotly, etc.) as long as they return the chart as PNG bytes. This enables
    integration of specialized visualizations not covered by built-in chart types.
    
    Attributes:
        type: Always "custom" for this chart type.
        chart_fn: User-provided function for chart generation.
        chart_config: Configuration dictionary passed to the custom function.
        
    Example:
        Defining and using a custom chart function:
        
        >>> def my_custom_chart(df, config, chart_instance):
        ...     import matplotlib.pyplot as plt
        ...     
        ...     # Create custom visualization
        ...     fig, ax = plt.subplots(figsize=(10, 6))
        ...     ax.plot(df[config['x_col']], df[config['y_col']])
        ...     ax.set_title(config.get('title', 'Custom Chart'))
        ...     
        ...     # Convert to PNG bytes
        ...     buf = io.BytesIO()
        ...     fig.savefig(buf, format='png', dpi=100)
        ...     plt.close(fig)
        ...     return buf.getvalue()
        ... 
        >>> chart = CustomChart(
        ...     type="custom",
        ...     chart_fn=my_custom_chart,
        ...     chart_config={
        ...         "x_col": "date",
        ...         "y_col": "value",
        ...         "title": "My Analysis"
        ...     },
        ...     data_source=csv_source
        ... )
    """
    
    type: Literal["custom"] = "custom"
    chart_fn: Annotated[Callable, Field(..., description = "Chart function resolved by ConfigLoader")]
    chart_config: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Configuration for the custom function")]
    
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate chart using the user-provided custom function.
        
        Applies data transformations, processes the configuration to replace
        column references, and calls the custom chart function with the prepared
        data and configuration.
        
        Args:
            df: DataFrame containing the chart data, already fetched from the
                data source if configured.
                
        Returns:
            PNG image bytes generated by the custom function.
            
        Raises:
            ChartGenerationError: If the custom function fails or returns
                invalid data.
                
        Example:
            >>> df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
            >>> image_bytes = custom_chart.generate_chart_image(df)
        """
        transformed_df = self.apply_data_transforms(df)

        chart_func = self.chart_fn

        processed_config = self._process_config(self.chart_config, transformed_df)

        processed_config['title'] = self.title

        return chart_func(transformed_df, processed_config, self)
    
    def _process_config(self, config: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        """Process configuration by replacing column references with data.
        
        Similar to PlotlyGraphObjects._process_trace_config but tailored for
        custom chart configurations. Replaces column references (strings starting
        with '$') with actual pandas Series or lists from the DataFrame.
        
        Args:
            config: Configuration dictionary that may contain column references
                in the format '$column_name'.
            df: DataFrame containing the referenced columns.
            
        Returns:
            Processed configuration with column references replaced by actual
            data, ready for use by the custom function.
            
        Raises:
            ChartGenerationError: If a referenced column doesn't exist in the
                DataFrame.
                
        Example:
            >>> config = {"x_data": "$months", "y_data": "$sales", "color": "blue"}
            >>> df = pd.DataFrame({"months": ["Jan", "Feb"], "sales": [100, 150]})
            >>> processed = chart._process_config(config, df)
            >>> # processed["x_data"] is now a pandas Series with ["Jan", "Feb"]
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
    """Chart type that generates visualizations from YAML templates.
    
    This chart type enables reusable chart configurations by loading chart
    definitions from YAML templates. Templates can define complex Plotly
    configurations with variable substitution, making it easy to create
    consistent chart styles across presentations.
    
    Templates are rendered using the Jinja2 template engine, allowing for
    dynamic configuration based on the provided template_config parameters.
    The rendered template must produce a valid PlotlyGraphObjects configuration.
    
    Attributes:
        type: Always "template" for this chart type.
        template_name: Name of the YAML template file to use.
        template_config: Parameters to pass to the template for rendering.
        
    Example:
        Using a template for consistent chart styling:
        
        >>> # templates/line_chart.yaml:
        >>> # traces:
        >>> #   - type: scatter
        >>> #     x: "${{ x_column }}"
        >>> #     y: "${{ y_column }}"
        >>> #     mode: lines+markers
        >>> #     name: "{{ series_name }}"
        >>> # layout_config:
        >>> #   title: "{{ title }}"
        >>> #   xaxis:
        >>> #     title: "{{ x_axis_label }}"
        >>> #   yaxis:
        >>> #     title: "{{ y_axis_label }}"
        >>> 
        >>> chart = TemplateChart(
        ...     type="template",
        ...     template_name="line_chart",
        ...     template_config={
        ...         "x_column": "date",
        ...         "y_column": "revenue",
        ...         "series_name": "Monthly Revenue",
        ...         "title": "Revenue Trend",
        ...         "x_axis_label": "Month",
        ...         "y_axis_label": "Revenue ($)"
        ...     },
        ...     data_source=revenue_data
        ... )
    """
    
    type: Literal["template"] = "template"
    template_name: Annotated[str, Field(..., description = "Name of the YAML template to use")]
    template_config: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Configuration for the template")]
    
    def generate_chart_image(self, df: pd.DataFrame) -> bytes:
        """Generate chart by rendering a YAML template to Plotly configuration.
        
        Renders the specified template with the provided configuration parameters,
        then creates a PlotlyGraphObjects chart with the rendered configuration.
        This allows for reusable, parameterized chart definitions.
        
        The template should render to a valid PlotlyGraphObjects configuration
        including 'traces' and optionally 'layout_config' and 'data_transforms'.
        
        Args:
            df: DataFrame containing the chart data, to be passed to the
                generated PlotlyGraphObjects instance.
                
        Returns:
            PNG image bytes of the chart generated from the template.
            
        Raises:
            TemplateNotFoundError: If the specified template doesn't exist.
            TemplateRenderError: If template rendering fails.
            ChartGenerationError: If the rendered configuration is invalid.
            
        Example:
            >>> # Assuming 'bar_chart' template exists
            >>> chart = TemplateChart(
            ...     template_name="bar_chart",
            ...     template_config={"category_col": "product", "value_col": "sales"}
            ... )
            >>> image_bytes = chart.generate_chart_image(sales_df)
        """

        engine = get_template_engine()
        
        # Render the template with user config
        rendered_config = engine.render_template(self.template_name, self.template_config)
        
        # Create a PlotlyGraphObjects chart with the rendered config
        # Combine user transforms with template transforms
        all_transforms = (self.data_transforms or []) + (rendered_config.get('data_transforms', []))
        
        plotly_chart = PlotlyGraphObjects(
            type = "plotly_go",
            data_source = None,  # We already have the data
            data_transforms = all_transforms,
            traces = rendered_config['traces'],
            layout_config = rendered_config.get('layout_config', {}),
            width = self.width,
            height = self.height,
            x = self.x,
            y = self.y,
            dimensions_format = self.dimensions_format
        )

        return plotly_chart.generate_chart_image(df)

ChartUnion = Annotated[
    Union[PlotlyGraphObjects, CustomChart, TemplateChart],
    Field(discriminator = "type")
]
"""Union type for all available chart types with discriminated validation.

This type alias enables Pydantic to automatically select and validate the
correct chart type based on the 'type' field in the configuration. It supports:

- PlotlyGraphObjects: For Plotly-based visualizations with 'type': 'plotly_go'
- CustomChart: For user-defined functions with 'type': 'custom'
- TemplateChart: For template-based charts with 'type': 'template'

Example:
    >>> from pydantic import TypeAdapter
    >>> 
    >>> # Automatically creates PlotlyGraphObjects instance
    >>> chart_config = {
    ...     "type": "plotly_go",
    ...     "traces": [{"type": "scatter", "x": "$x", "y": "$y"}]
    ... }
    >>> adapter = TypeAdapter(ChartUnion)
    >>> chart = adapter.validate_python(chart_config)
"""
