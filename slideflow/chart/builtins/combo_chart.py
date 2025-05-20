import pandas as pd
import plotly.graph_objects as go
from typing import Any, Callable, Dict, Optional, Literal, List
from pydantic import BaseModel, Field, root_validator

from slideflow.chart.builtins.common import BuiltinChartType, ChartConfig
from slideflow.chart.builtins.utils.color import BUILTIN_COLOR_FUNCTIONS
from slideflow.chart.builtins.utils.format import BUILTIN_FORMAT_FUNCTIONS

BUILTIN_FUNCTIONS = BUILTIN_COLOR_FUNCTIONS | BUILTIN_FORMAT_FUNCTIONS

class TraceConfig(BaseModel):
    """
    Configuration for an individual trace (bar or line) in a combo chart.

    Attributes:
        name (str): Label to display in the chart legend.
        trace_type (str): Type of trace — 'bar' or 'scatter' (line/marker).
        x_col (str): Name of the DataFrame column to use for the x-axis.
        y_col (str): Name of the DataFrame column to use for the y-axis.
        axis (str): 'primary' or 'secondary' y-axis assignment.
        mode (Optional[str]): For scatter traces — 'lines', 'markers', or 'lines+markers'.
        marker_color (Optional[str]): Fill color for the bar or scatter markers.
        line (dict): Line styling dictionary for scatter traces.
    """
    name: str = Field(..., description="Legend label", example="GMV Current")
    trace_type: Literal['bar', 'scatter'] = 'scatter'
    x_col: str = Field(..., description="X Column", example="week_number")
    y_col: str = Field(..., description="Y Column", example="gmv_curr_year")
    axis: Literal['primary', 'secondary'] = 'primary'
    mode: Optional[str] = None
    marker_color: Optional[str] = None
    line: Dict[str, Any] = Field(default_factory=dict)


class ComboChartLayout(BaseModel):
    """
    Layout and styling configuration for combo charts.

    Attributes:
        title Optional(str): Optional Chart title text.
        xaxis_title Optional(str): Optional Label for the x-axis.
        yaxis_primary_title Optional(str): Optional Label for the primary (left) y-axis.
        yaxis_secondary_title Optional(str): Optional Label for the secondary (right) y-axis.
        font_size (int): Base font size for labels and axis text. Defaults to 8.
        legend_font_size (int): Font size for the legend labels. Defaults to 6.
        margin (dict): Margin sizes (left, right, top, bottom) in pixels. Defaults to top: 5 and bottom: 50.
        plot_bgcolor (str): Background color of the plot area. Defaults to 'white'.
        x_showticklabels (bool): Whether to show tick labels on the x-axis. Defaults to True.
        y_showticklabels (bool): Whether to show tick labels on the y-axis. Defaults to True.
        x_tickformat (Optional[str]): Optional Plotly tick formatting string for the x-axis.
        yaxis_primary_tickformat (Optional[str]): Optional Plotly tick formatting string for the primary y-axis (Left).
        yaxis_secondary_tickformat (Optional[str]): Optional Plotly tick formatting string for the secondary y-axis (Right).
        tickfont (dict): Font styling for tick labels (e.g., size, color).
        x_show_grid (bool): Whether to show vertical grid lines (x-axis). Defaults to False.
        y_show_grid (bool): Whether to show horizontal grid lines (y-axis). Defaults to False.
        x_zero_line (bool): Whether to show a zero line on the x-axis. Defaults to False.
        y_zero_line (bool): Whether to show a zero line on the y-axis. Defaults to False.
        grid_line_width (Float): Sets the thickness in pixels of the x and y gridlines. Defaults to 0.5.
        grid_line_color (str): Sets the colour of the gridlines. Defaults to #999 (Grey).
    """
    title: Optional[str] = None
    xaxis_title: Optional[str] = None
    yaxis_primary_title: Optional[str] = None
    yaxis_secondary_title: Optional[str] = None
    font_size: int = 8
    legend_font_size: int = 6
    margin: Dict[str, int] = Field(default_factory=lambda: {'l': 0, 'r': 0, 't': 5, 'b': 50})
    plot_bgcolor: str = 'white'
    x_showticklabels: bool = True
    y_showticklabels: bool = True
    x_tickformat: Optional[str] = None
    yaxis_primary_tickformat: Optional[str] = None
    yaxis_secondary_tickformat: Optional[str] = None
    tickfont: Dict[str, Any] = Field(default_factory=lambda: {'size': 8, 'color': 'black'})
    x_show_grid: bool = False
    y_show_grid: bool = False
    x_zero_line: bool = False
    y_zero_line: bool = False
    grid_line_width: float = 0.5
    grid_line_color: str = '#999'



class ComboChartConfig(BaseModel):
    """
    Top-level configuration for a combo chart.

    Attributes:
        chart_type (str): Type of chart. Should always be 'combo_chart'.
        dual_axis (bool): Whether to enable a secondary y-axis (on the right). Defaults to False.
        traces (List[TraceConfig]): List of trace configurations to plot.
        layout (ComboChartLayout): Layout and styling options for the chart.
        preprocess_fn (Callable): Optional preprocessing function to apply to the data.
        preprocess_fn_args (dict): Arguments to pass into the `preprocess_fn`.
    """
    chart_type: BuiltinChartType = Field('combo_chart', description="Type of chart. Should be 'combo_chart'")
    dual_axis: bool = False
    traces: List[TraceConfig]
    layout: ComboChartLayout = ComboChartLayout()
    preprocess_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None
    preprocess_fn_args: Optional[Dict[str, str]] = Field(default_factory=dict)

    def resolve_args(self, params: dict[str, str]) -> None:
        if self.preprocess_fn_args:
            self.preprocess_fn_args = {
                k: v.format(**params) if isinstance(v, str) else v
                for k, v in self.preprocess_fn_args.items()
            }


def create_configurable_combo_chart(df: pd.DataFrame, config: ComboChartConfig) -> go.Figure:
    
    df = df.copy()

    if config.preprocess_fn:
        try:
            df = config.preprocess_fn(df, **config.preprocess_fn_args)
        except Exception as e:
            raise RuntimeError(f'Failed to call preprocess_fn with args {config.preprocess_fn_args}: {e}')

    fig = go.Figure()

    for traces in config.traces:
        kwargs = dict(
            x = df[traces.x_col],
            y = df[traces.y_col],
            name = traces.name,
            marker_color = traces.marker_color
        )

        if traces.trace_type == 'bar':
            trace = go.Bar(**kwargs)
        elif traces.trace_type == 'scatter':
            trace = go.Scatter(**kwargs, mode=traces.mode or 'lines', line=traces.line)
        else:
            raise ValueError(f'Unsupported trace_type: {traces.trace_type}')

        want_yaxis = 'y' if not config.dual_axis or traces.axis == 'secondary' else 'y2'
        trace.update(yaxis=want_yaxis)
        fig.add_trace(trace)

    xaxis_config = dict(
        showgrid = config.layout.x_show_grid,
        gridwidth = config.layout.grid_line_width,
        gridcolor = config.layout.grid_line_color,
        zeroline = config.layout.x_zero_line,
        showticklabels = config.layout.x_showticklabels,
        tickformat = config.layout.x_tickformat,
        tickfont = config.layout.tickfont,
        title = config.layout.xaxis_title
    )

    yaxis_config = dict(
        showgrid = config.layout.y_show_grid,
        gridwidth = config.layout.grid_line_width,
        gridcolor = config.layout.grid_line_color,
        zeroline = config.layout.y_zero_line,
        showticklabels = config.layout.y_showticklabels,
        tickformat = config.layout.yaxis_primary_tickformat,
        tickfont = config.layout.tickfont,
        title = config.layout.yaxis_primary_title,
        side = 'left'
    )

    layout_kwargs = dict(
        title = config.layout.title,
        xaxis = xaxis_config,
        yaxis = yaxis_config,
        legend = dict(
            orientation = 'h', yanchor = 'bottom', y = 1.02,
            xanchor = 'left', x = 0,
            font = dict(size = config.layout.legend_font_size)
        ),
        margin = config.layout.margin,
        plot_bgcolor = config.layout.plot_bgcolor,
        font = dict(size = config.layout.font_size)
    )

    if config.dual_axis:
        layout_kwargs['yaxis2'] = dict(
            title = config.layout.yaxis_primary_title,
            side = 'left',
            overlaying = 'y',
            showgrid = False,
            tickformat = config.layout.yaxis_primary_tickformat
        )
        layout_kwargs['yaxis']['title'] = config.layout.yaxis_secondary_title
        layout_kwargs['yaxis']['side']  = 'right'
        layout_kwargs['yaxis']['tickformat'] = config.layout.yaxis_secondary_tickformat

    fig.update_layout(**layout_kwargs)
    return fig