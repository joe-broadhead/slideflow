import pandas as pd
import plotly.graph_objects as go
from pydantic import BaseModel, Field
from typing import Any, Callable, Dict, List, Literal, Optional

from slideflow.chart.builtins.common import ChartConfig
from slideflow.utils.formatting.color import BUILTIN_COLOR_FUNCTIONS
from slideflow.utils.formatting.format import BUILTIN_FORMAT_FUNCTIONS

class LineSeriesConfig(BaseModel):
    """
    Configuration for an individual line in a line chart.

    This model specifies how a single line should be rendered in a chart, 
    including its data columns, styling, and rendering mode.

    Attributes:
        name (str):  
            Name of the series, used for the legend and labeling.
        
        x_col (str):  
            Name of the column in the DataFrame to use for x-axis values.
        
        y_col (str):  
            Name of the column in the DataFrame to use for y-axis values.
        
        line_color (Optional[str]):  
            Color of the line. Can be any valid Plotly color string (e.g., "#ff0000", "blue").
        
        line_dash (Optional[Literal['solid', 'dot', 'dash']]):  
            Dash style of the line. One of `'solid'`, `'dot'`, or `'dash'`. Defaults to `'solid'`.
        
        line_width (Optional[int]):  
            Width of the line in pixels. Defaults to 2.
        
        mode (Literal['lines', 'lines+markers']):  
            Plot mode. Use `'lines'` for a continuous line or `'lines+markers'` to show both lines and data point markers.
            Defaults to `'lines'`.
    """
    name: str = Field(..., description = 'Name of the series (used for legend and label).')
    x_col: str = Field(..., description = 'Column to use for the x-axis.')
    y_col: str = Field(..., description = 'Column to use for the y-axis.')
    line_color: Optional[str] = Field(default = None, description = 'Color of the line.')
    line_dash: Optional[Literal['solid', 'dot', 'dash']] = Field(default = 'solid', description = 'Dash style of the line.')
    line_width: Optional[int] = Field(default = 2, description ='Width of the line.')
    mode: Literal['lines', 'lines+markers'] = Field(default = 'lines', description = 'Plot mode for the line.')


class LineChartConfig(ChartConfig):
    """
    Configuration for rendering a configurable multi-series line chart.

    This model defines the structure and styling options for creating line charts
    with one or more series, along with chart-level layout customizations.

    Attributes:
        chart_type (Literal['line']):  
            Chart type identifier. Must be 'line'. Used internally for chart selection.
        
        series (List[LineSeriesConfig]):  
            A list of line series to render. Each series defines its own data columns and style.
        
        title (Optional[str]):  
            Title text displayed at the top of the chart. Defaults to "Line Chart".
        
        xaxis_title (Optional[str]):  
            Title label for the x-axis. Optional.
        
        yaxis_title (Optional[str]):  
            Title label for the y-axis. Optional.
        
        height (Optional[int]):  
            Height of the chart in pixels. Optional.
        
        width (Optional[int]):  
            Width of the chart in pixels. Optional.
        
        showlegend (bool):  
            Whether to display the legend on the chart. Defaults to True.
        
        template (str):  
            Name of the Plotly theme to use. Common options include `'plotly_white'`, `'plotly'`, `'ggplot2'`, etc.  
            Defaults to `'plotly_white'`.
        
        paper_bgcolor (Optional[str]):  
            Background color of the overall canvas (outside the plot area).
        
        plot_bgcolor (Optional[str]):  
            Background color inside the plot area (behind the lines).
        
        font_family (Optional[str]):  
            Font family to use for all text in the chart (e.g., `'Helvetica'`).
        
        font_color (Optional[str]):  
            Font color for all text in the chart (e.g., `'black'`, `'white'`).
        
        preprocess_functions (List[Dict[str, Any]]):
            A list of preprocessing steps to apply to the data before rendering. Each step includes a function reference and optional arguments, allowing for filtering, grouping, or transforming the data prior to display.
    """
    chart_type: Literal['line'] = Field(default = "line", description = "Chart type identifier. Must be 'line'.")
    series: List[LineSeriesConfig] = Field(..., description = 'List of individual line series to plot on the chart.')
    title: Optional[str] = Field(default = 'Line Chart', description = 'Chart title text.')
    xaxis_title: Optional[str] = Field(default = None, description = 'Title for the x-axis.')
    yaxis_title: Optional[str] = Field(default = None, description = 'Title for the y-axis.')
    height: Optional[int] = Field(default = None, description = 'Height of the chart in pixels.')
    width: Optional[int] = Field(default = None, description = 'Width of the chart in pixels.')
    showlegend: bool = Field(default = True, description = 'Whether to display the legend.')
    template: str = Field(default = 'plotly_white', description = "Plotly theme template (e.g. 'plotly', 'plotly_white', 'ggplot2').")
    paper_bgcolor: Optional[str] = Field(default = None, description = 'Background color of the chart canvas (outside plot area).')
    plot_bgcolor: Optional[str] = Field(default = None, description = "Background color inside the chart's plotting area.")
    font_family: Optional[str] = Field(default = None, description = "Font family for all text in the chart (e.g., 'Helvetica').")
    font_color: Optional[str] = Field(default = None, description = "Font color for all chart text (e.g., 'white').")
    preprocess_functions: List[Dict[str, Any]] = Field(default_factory=list, description = 'Optional function to preprocess the DataFrame before rendering. Takes and returns a DataFrame.')

    def resolve_args(self, params: dict[str, str]) -> None:
        """
        Updates preprocess_fn_args by formatting any string values with the provided params.

        Args:
            params (dict[str, str]): Parameters to use for string interpolation.
        """
        if hasattr(self, "preprocess_functions"):
            for step in self.preprocess_functions:
                if "args" in step:
                    for k, v in step["args"].items():
                        if isinstance(v, str):
                            step["args"][k] = v.format(**params)


def create_configurable_line(df: pd.DataFrame, config: LineChartConfig = LineChartConfig) -> go.Figure:
    """
    Creates a configurable multi-series line chart using Plotly.

    This function builds a `plotly.graph_objects.Figure` based on a list of line
    series and chart-level layout options defined in the `LineChartConfig`. Each series
    specifies its own x/y columns and line style. Chart appearance and layout can be customized
    via colors, font, dimensions, and templates.

    Args:
        df (pd.DataFrame): 
            The input data containing all columns referenced by the chart configuration.
        
        config (LineChartConfig): 
            A configuration object that defines the series to plot, styling options, layout
            attributes, and optional preprocessing.

    Returns:
        go.Figure: 
            A fully configured Plotly `Figure` object representing the line chart.

    Raises:
        RuntimeError: If the optional preprocessing function raises an error.
    """
    df = df.copy()

    if config.preprocess_functions:
        for step in config.preprocess_functions:
            fn_name = step["function"]
            args = step.get("args", {})
            df = fn_name(df, **args)

    fig = go.Figure()

    for series_cfg in config.series:
        fig.add_trace(go.Scatter(
            name = series_cfg.name,
            x = df[series_cfg.x_col],
            y = df[series_cfg.y_col],
            mode = series_cfg.mode,
            line = dict(
                color = series_cfg.line_color,
                dash = series_cfg.line_dash,
                width = series_cfg.line_width
            )
        ))

    fig.update_layout(
        title = config.title,
        xaxis_title = config.xaxis_title,
        yaxis_title = config.yaxis_title,
        height = config.height,
        width = config.width,
        showlegend = config.showlegend,
        template = config.template,
        paper_bgcolor = config.paper_bgcolor,
        plot_bgcolor = config.plot_bgcolor,
        font=dict(
            family = config.font_family,
            color = config.font_color
        ) if config.font_family or config.font_color else None
    )

    return fig
