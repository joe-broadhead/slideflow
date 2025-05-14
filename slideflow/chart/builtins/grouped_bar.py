import pandas as pd
import plotly.graph_objects as go
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, Field, root_validator

from slideflow.chart.builtins.common import BuiltinChartType, ChartConfig
from slideflow.chart.builtins.utils.color import BUILTIN_COLOR_FUNCTIONS
from slideflow.chart.builtins.utils.format import BUILTIN_FORMAT_FUNCTIONS

BUILTIN_FUNCTIONS = BUILTIN_COLOR_FUNCTIONS | BUILTIN_FORMAT_FUNCTIONS

class GroupedBarMarkerConfig(BaseModel):
    """
    Configuration for styling and formatting grouped bar charts.

    Attributes:
        x_showgrid (bool): Whether to display vertical grid lines along the x-axis. Defaults to True
        y_showgrid (bool): Whether to display horizontal grid lines along the y-axis. Defaults to False
        color_current (str): Fill color for the current year bars. Defaults to '#3333CC'.
        color_previous (str): Fill color for the previous year bars. Defaults to '#CCCCFF'.
        line_width (float): Width of the border line around each bar (in pixels). Defaults to 0.5.
        line_color (str): Color of the border line around each bar. Defaults to #999 (Grey).
        zeroline (bool): Whether to display a zero-line on the x-axis (if applicable). Defaults to False.
        bar_width (float): Thickness of each bar. Defaults to 0.2.
    """
    x_showgrid: bool = True
    y_showgrid: bool = False
    color_current: str = '#3333CC'
    color_previous: str = '#CCCCFF'
    line_width: float = 0.5
    line_color: str = '#999'
    zeroline: bool = False
    bar_width: float = 0.2

class GroupedBarLayoutConfig(BaseModel):
    """
    Configuration for the layout of a bar chart, including dimensions, titles, and styling.

    Attributes:
        margin (Dict[str, int]): Margin around the chart. Keys include 'l', 'r', 't', 'b' for left, right, top, and bottom.
        height (int): Height of the chart in pixels. Default is 600.
        width (int): Width of the chart in pixels. Default is 350.
        plot_bgcolor (str): Background color of the plot area. Default is 'white'.
        title (Optional[str]): Optional title for the chart.
        title_font (Dict[str, Any]): Font styling for the title, including size and color.
        xaxis_title (Optional[str]): Optional title for the x-axis.
        yaxis_title (Optional[str]): Optional title for the y-axis.
        xaxis_title_font (dict): Font style for the x-axis title (e.g. {'size': 8, 'weight': 700}).
        x_showticklabels (bool): Displaying of tick labels for x-axis. Defaults to True.
        y_showticklabels (bool): Displaying of tick labels for y-axis. Defaults to True.
        x_tickformat (Optional[str]): Plotly tick format string for x-axis (e.g., '.0%', ',.2f').
        y_tickformat (Optional[str]): Plotly tick format string for y-axis.
        label_current (str): Legend label for the current year bar trace.
        label_previous (str): Legend label for the previous year bar trace.
        show_legend (bool): Whether to display the legend. Defaults to True.
        legend_font_size (int): Font size for legend text. Defaults to 6.
    """
    margin: Dict[str, int] = Field(default_factory = lambda: {'l': 0, 'r': 0, 't': 5, 'b': 50})
    height: int = 600
    width: int = 350
    plot_bgcolor: str = 'white'
    title: Optional[str] = None
    title_font: Dict[str, Any] = Field(default_factory = lambda: {'size': 16, 'color': 'black'})
    xaxis_title: Optional[str] = None
    yaxis_title: Optional[str] = None
    xaxis_title_font: Dict[str, Any] = Field(default_factory = lambda: {'size': 8, 'weight': 700})
    tickfont: int = 8
    x_showticklabels: bool = True
    y_showticklabels: bool = True
    x_tickformat: Optional[str] = None
    y_tickformat: Optional[str] = None
    label_current: Optional[str] = Field(None, description='Label for the current bar trace')
    label_previous: Optional[str] = Field(None, description='Label for the previous bar trace')
    show_legend: bool = True
    legend_font_size: int = 6

class GroupedBarChartConfig(ChartConfig):
    """
    Configuration for a bar chart including data mapping, formatting, sorting, and layout options.

    Attributes:
        chart_type (str): Type of chart. Should always be 'bar'.
        x_col (str): Name of the DataFrame column to use for x-axis values.
        y_col (str): Name of the DataFrame column to use for y-axis labels.
        orientation (str): Bar orientation. Use 'h' for horizontal or 'v' for vertical.
        sort_by (Optional[str]): Column name to sort the DataFrame by. If None, no sorting is applied.
        sort_ascending (bool): If True, sort in ascending order. Defaults to False (descending).
        textposition (str): Position of the text labels relative to bars (e.g. 'outside').
        marker (BarMarkerConfig): Configuration for bar color and border styling.
        layout (BarLayoutConfig): Layout configuration for the chart (e.g. size, margins, title).
        x_range_multiplier (float): Multiplier to extend the axis range beyond the maximum value.
        preprocess_fn (Optional[Callable[[pd.DataFrame], pd.DataFrame]]): Optional preprocessing function to modify the DataFrame before plotting.
        preprocess_fn_args (Optional[Dict[str, str]]): Parameters to pass into the `preprocess_fn`.
    """
    chart_type: BuiltinChartType = Field('grouped_bar', description = "Type of chart. Should be 'grouped_bar'")
    x_col_current: str = Field(..., description = 'DataFrame column to use for x-axis values.')
    x_col_previous: str = Field(..., description = 'DataFrame column to use for x-axis values.')
    y_col: str = Field(..., description = 'DataFrame column to use for y-axis labels.')
    sort_by: Optional[str] = Field(None, description = 'Column to sort the DataFrame by. If not provided, no sorting is applied.')
    sort_ascending: bool = Field(False, description = 'Sort order. Defaults to descending order if False.')
    marker: GroupedBarMarkerConfig = Field(default_factory = GroupedBarMarkerConfig)
    layout: GroupedBarLayoutConfig = Field(default_factory = GroupedBarLayoutConfig)
    x_range_multiplier: float = Field(1.5, description = 'Multiplier for axis range based on maximum value.')
    preprocess_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = Field(
        None,
        description = 'Optional function to preprocess the DataFrame before rendering.'
    )
    preprocess_fn_args: Optional[Dict[str, str]] = Field(default_factory = dict)


    def resolve_args(self, params: dict[str, str]) -> None:
        """
        Updates preprocess_fn_args by formatting any string values with the provided params.

        Args:
            params (dict[str, str]): Parameters to use for string interpolation.
        """
        if self.preprocess_fn_args:
            self.preprocess_fn_args = {
                k: v.format(**params) if isinstance(v, str) else v
                for k, v in self.preprocess_fn_args.items()
            }

def create_configurable_grouped_bar(df: pd.DataFrame, config: GroupedBarChartConfig = GroupedBarChartConfig) -> go.Figure:
    """
    Generates a configurable Plotly bar chart based on the provided DataFrame and chart configuration.

    This function supports:
    - Preprocessing the DataFrame via a user-defined function.
    - Dynamic sorting.
    - Dynamic labeling with optional formatters.
    - Layout customization including size, orientation, titles, colors, and axis configuration.

    Args:
        df (pd.DataFrame): The input data used to render the chart.
        config (BarChartConfig): Configuration object defining how the chart should be rendered.

    Returns:
        go.Figure: A Plotly Figure object representing the generated bar chart.

    Raises:
        RuntimeError: If the `preprocess_fn` fails when called with provided arguments.
    """
    df = df.copy()

    if config.preprocess_fn:
        try:
            df = config.preprocess_fn(df, **config.preprocess_fn_args)
        except Exception as e:
            raise RuntimeError(f'Failed to call preprocess_fn with args {config.preprocess_fn_args}: {e}')

    if config.sort_by:
        df = df.sort_values(by = config.sort_by, ascending = config.sort_ascending)

    fig = go.Figure()

    #Previous trace
    fig.add_trace(go.Bar(
        y = df[config.y_col],
        x = df[config.x_col_previous],
        name = config.layout.label_previous,
        orientation = 'h',
        legendgroup = 'previous',
        showlegend = config.layout.show_legend,
        width = config.marker.bar_width,
        marker = dict(
            color = config.marker.color_previous,
            line = dict(width = 0)
        )
    ))

    #Current trace
    fig.add_trace(go.Bar(
        y = df[config.y_col],
        x = df[config.x_col_current],
        name = config.layout.label_current,
        orientation = 'h',
        legendgroup = 'current',
        showlegend = config.layout.show_legend,
        width = config.marker.bar_width,
        marker = dict(
            color = config.marker.color_current,
            line = dict(width = 0)
        )
    ))

    fig.update_layout(
        barmode = 'group',
        xaxis_title = config.layout.xaxis_title,
        xaxis_title_font = config.layout.xaxis_title_font,
        xaxis = dict(
            tickfont = dict(
                size = config.layout.tickfont
            ),
            showgrid = config.marker.x_showgrid,
            gridcolor = config.marker.line_color,
            gridwidth = config.marker.line_width,
            zeroline = config.marker.zeroline
        ),
        yaxis = dict(
            tickfont = dict(
                size = config.layout.tickfont
            ),
            showgrid = config.marker.y_showgrid
        ),
        legend = dict(
            font = dict(
                size = config.layout.legend_font_size                
            ),
            orientation = 'h',
            yanchor = 'bottom',
            y = 1.02,
            xanchor = 'left',
            x = 0,
            itemsizing = 'constant',
            borderwidth = 0,
            bgcolor = 'rgba(0,0,0,0)'
        ),
        margin = config.layout.margin,
        plot_bgcolor = config.layout.plot_bgcolor
    )

    return fig
