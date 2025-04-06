import pandas as pd
import plotly.graph_objects as go
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, Field, root_validator

from slideflow.chart.builtins.utils.color import BUILTIN_COLOR_FUNCTIONS
from slideflow.chart.builtins.utils.format import BUILTIN_FORMAT_FUNCTIONS

BUILTIN_FUNCTIONS = BUILTIN_COLOR_FUNCTIONS | BUILTIN_FORMAT_FUNCTIONS

class BarMarkerConfig(BaseModel):
    """
    Configuration for styling the bars in a bar chart.

    Attributes:
        color (str): The fill color of the bars. Default is '#3643bb'.
        line_width (int): The width of the outline around each bar. Default is 1.
        line_color (str): The color of the bar outline. Default is 'white'.
    """
    color: str = '#3643bb'
    line_width: int = 1
    line_color: str = 'white'

class BarLayoutConfig(BaseModel):
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
    """
    margin: Dict[str, int] = Field(default_factory = lambda: {'l': 0, 'r': 0, 't': 5, 'b': 50})
    height: int = 600
    width: int = 350
    plot_bgcolor: str = 'white'
    title: Optional[str] = None
    title_font: Dict[str, Any] = Field(default_factory = lambda: {'size': 16, 'color': 'black'})
    xaxis_title: Optional[str] = None
    yaxis_title: Optional[str] = None

class BarChartConfig(BaseModel):
    """
    Configuration for a bar chart including data mapping, formatting, sorting, and layout options.

    Attributes:
        chart_type (str): Type of chart. Should always be 'bar'.
        x_col (str): Name of the DataFrame column to use for x-axis values.
        y_col (str): Name of the DataFrame column to use for y-axis labels.
        orientation (str): Bar orientation. Use 'h' for horizontal or 'v' for vertical.
        sort_by (Optional[str]): Column name to sort the DataFrame by. If None, no sorting is applied.
        sort_ascending (bool): If True, sort in ascending order. Defaults to False (descending).
        text_formatter (Callable[[Any], str]): Function to format text labels on bars.
        text_formatter_args (Optional[Dict[str, Any]]): Optional arguments to pass to the text formatter.
        textposition (str): Position of the text labels relative to bars (e.g. 'outside').
        marker (BarMarkerConfig): Configuration for bar color and border styling.
        layout (BarLayoutConfig): Layout configuration for the chart (e.g. size, margins, title).
        x_range_multiplier (float): Multiplier to extend the axis range beyond the maximum value.
        preprocess_fn (Optional[Callable[[pd.DataFrame], pd.DataFrame]]): Optional preprocessing function to modify the DataFrame before plotting.
        preprocess_fn_args (Optional[Dict[str, str]]): Parameters to pass into the `preprocess_fn`.
        text_col (Optional[str]): Optional column name to use for text labels. If not provided, defaults to `x_col` for horizontal charts and `y_col` for vertical charts.
    """
    chart_type: str = Field('bar', description = "Type of chart. Should be 'bar'")
    x_col: str = Field(..., description = 'DataFrame column to use for x-axis values.')
    y_col: str = Field(..., description = 'DataFrame column to use for y-axis labels.')
    orientation: str = Field('h', description = "Bar orientation: 'h' for horizontal, 'v' for vertical.")
    sort_by: Optional[str] = Field(None, description = 'Column to sort the DataFrame by. If not provided, no sorting is applied.')
    sort_ascending: bool = Field(False, description = 'Sort order. Defaults to descending order if False.')
    text_formatter: Callable[[Any], str] = Field(default = lambda x: str(x), description = 'Function to format text labels for bars.')
    text_formatter_args: Optional[Dict[str, Any]] = Field(default_factory = dict)
    textposition: str = Field('outside', description = 'Text position relative to bars.')
    marker: BarMarkerConfig = Field(default_factory = BarMarkerConfig)
    layout: BarLayoutConfig = Field(default_factory = BarLayoutConfig)
    x_range_multiplier: float = Field(1.5, description = 'Multiplier for axis range based on maximum value.')
    preprocess_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = Field(
        None,
        description = 'Optional function to preprocess the DataFrame before rendering.'
    )
    preprocess_fn_args: Optional[Dict[str, str]] = Field(default_factory = dict)
    text_col: Optional[str] = Field(
        None,
        description = 'Optional column to use for text labels. Defaults to x_col for horizontal and y_col for vertical charts.'
    )

    @root_validator(pre = True)
    def resolve_function_names(cls, values):
        """
        Resolves string names of functions to actual callables using the BUILTIN_FUNCTIONS registry.

        This validator runs before model initialization and replaces string references to functions
        (e.g., 'abbreviate') with their actual callable counterparts from the registry.

        Args:
            values (dict): The input dictionary of field values before validation.

        Returns:
            dict: The updated dictionary with function references resolved.

        Raises:
            ValueError: If a provided function name is not found in the BUILTIN_FUNCTIONS registry.
        """
        for key in ['text_formatter']:
            if isinstance(values.get(key), str):
                func_name = values[key]
                if func_name not in BUILTIN_FUNCTIONS:
                    raise ValueError(f'Unknown function: {func_name}')
                values[key] = BUILTIN_FUNCTIONS[func_name]
        return values

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

def create_configurable_bar(df: pd.DataFrame, config: BarChartConfig = BarChartConfig) -> go.Figure:
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

    if config.text_col is not None:
        text_series = df[config.text_col]
    else:
        text_series = df[config.x_col] if config.orientation == 'h' else df[config.y_col]

    bar = go.Bar(
        x = df[config.x_col],
        y = df[config.y_col],
        orientation = config.orientation,
        text = [config.text_formatter(val, **config.text_formatter_args) for val in text_series],
        textposition = config.textposition,
        marker = dict(
            color = config.marker.color,
            line = dict(width = config.marker.line_width, color = config.marker.line_color)
        )
    )
    
    fig = go.Figure(data = [bar])

    layout_kwargs = dict(
        margin = config.layout.margin,
        height = config.layout.height,
        width = config.layout.width,
        plot_bgcolor = config.layout.plot_bgcolor,
        xaxis_title = config.layout.xaxis_title,
        yaxis_title = config.layout.yaxis_title,
    )
    if config.layout.title:
        layout_kwargs['title'] = {
            'text': config.layout.title,
            'font': config.layout.title_font,
            'x': 0.5  # center the title
        }
    fig.update_layout(**layout_kwargs)

    if config.orientation == 'h':
        fig.update_layout(
            yaxis=dict(showgrid = False, autorange = 'reversed'),
            xaxis=dict(showgrid = False, zeroline = False)
        )
        x_min = df[config.x_col].min() if not df[config.x_col].empty else 0
        x_max = df[config.x_col].max() if not df[config.x_col].empty else 0
        # Use the minimum if it is negative; otherwise, start from zero.
        if x_min < 0:
            fig.update_xaxes(range = [x_min * config.x_range_multiplier, x_max * config.x_range_multiplier])
        else:
            fig.update_xaxes(range = [0, x_max * config.x_range_multiplier])
    else:
        fig.update_layout(
            xaxis = dict(showgrid = False, zeroline = False),
            yaxis = dict(showgrid = False)
        )
        y_min = df[config.y_col].min() if not df[config.y_col].empty else 0
        y_max = df[config.y_col].max() if not df[config.y_col].empty else 0
        if y_min < 0:
            fig.update_yaxes(range=[y_min * config.x_range_multiplier, y_max * config.x_range_multiplier])
        else:
            fig.update_yaxes(range=[0, y_max * config.x_range_multiplier])

    return fig
