import pandas as pd
import plotly.graph_objects as go
from pydantic import BaseModel, Field
from typing import Any, Callable, Dict, Optional, Literal

from slideflow.chart.builtins.common import ChartConfig

class WaterfallMarkerStyle(BaseModel):
    """
    Configuration for styling markers in a Plotly waterfall chart.

    This class allows customization of marker colors and outlines for 
    increasing, decreasing, and total bars in a waterfall chart.

    Attributes:
        color (Optional[str]): 
            Fill color of the bar. Can be any valid CSS color string (e.g., "#1ceadd", "blue").

        line_color (Optional[str]): 
            Color of the outline (border) of the bar. If not specified, defaults to the fill color.

        line_width (Optional[int]): 
            Width of the bar outline in pixels. Defaults to 1.
    """
    color: Optional[str] = None
    line_color: Optional[str] = None
    line_width: Optional[int] = 1

class WaterfallConnectorStyle(BaseModel):
    """
    Configuration for connector lines between bars in a Plotly waterfall chart.

    This class allows you to customize the appearance of the lines that connect
    each bar in a waterfall chart (e.g., to emphasize flow or grouping).

    Attributes:
        color (str): 
            Color of the connector line. Accepts any valid CSS color string.
            Defaults to `'gray'`.

        width (Optional[int]): 
            Thickness of the connector line in pixels. Defaults to `1`.

        dash (Optional[Literal['solid', 'dot', 'dash']]): 
            Line style of the connector. Choose from `'solid'`, `'dot'`, or `'dash'`.
            Defaults to `None` (uses the default solid line).
    """
    color: str = Field(default = 'gray', description = 'Connector line color.')
    width: Optional[int] = Field(default = 1, description = 'Connector line width.')
    dash: Optional[Literal['solid', 'dot', 'dash']] = Field(
        default = None, 
        description = "Dash style for connector line: 'solid', 'dot', or 'dash'."
    )

class WaterfallConfig(ChartConfig):
    """
    Configuration for creating a Plotly waterfall chart.

    This class defines all customizable aspects of a waterfall chart, 
    including data mappings, layout, styling, and preprocessing logic. 
    It is designed to be flexible for both simple and highly customized charts.

    Attributes:
        x_col (str): 
            Column to use for the x-axis categories (e.g., 'Step', 'Country').

        y_col (str): 
            Column to use for the y-axis values (e.g., revenue change per category).

        xaxis_title (Optional[str]): 
            Title for the x-axis. Optional.

        yaxis_title (Optional[str]): 
            Title for the y-axis. Optional.

        height (Optional[int]): 
            Height of the chart in pixels. Optional.

        width (Optional[int]): 
            Width of the chart in pixels. Optional.

        measure_col (Optional[str]): 
            Column name that defines bar types (e.g., 'relative', 'total', 'absolute').

        orientation (Literal['v', 'h']): 
            Chart orientation: 'v' for vertical bars or 'h' for horizontal. Defaults to 'v'.

        title (Optional[str]): 
            Title of the chart. Defaults to "Waterfall Chart".

        waterfall_gap (float): 
            Gap between bars in the waterfall chart. Defaults to 0.03.

        increasing (Optional[WaterfallMarkerStyle]): 
            Styling options for increasing bars (positive changes).

        decreasing (Optional[WaterfallMarkerStyle]): 
            Styling options for decreasing bars (negative changes).

        totals (Optional[WaterfallMarkerStyle]): 
            Styling options for total bars.

        connector (Optional[WaterfallConnectorStyle]): 
            Styling options for the connectors between bars. Defaults to a gray line.

        text_col (Optional[str]): 
            Column containing label text for each bar. Optional.

        text_position (Optional[str]): 
            Position of the text labels on the bars (e.g., 'inside', 'outside', 'auto').

        showlegend (bool): 
            Whether to show the legend in the chart. Defaults to False.

        template (str): 
            Name of the Plotly template to use. Defaults to 'plotly_white'.

        paper_bgcolor (Optional[str]): 
            Background color of the chart paper. Optional.

        plot_bgcolor (Optional[str]): 
            Background color of the chart plot area. Optional.

        font_family (Optional[str]): 
            Font family used for chart text. Optional.

        font_color (Optional[str]): 
            Font color for all text in the chart. Optional.

        preprocess_fn (Optional[Callable[[pd.DataFrame], pd.DataFrame]]): 
            Optional preprocessing function to apply to the input DataFrame before plotting.

        preprocess_fn_args (Optional[Dict[str, Any]]): 
            Dictionary of keyword arguments to pass to the preprocessing function.
    """
    x_col: str = Field(..., description = 'Column to use for the x-axis (categories).')
    y_col: str = Field(..., description = 'Column to use for the y-axis (values).')
    
    xaxis_title: Optional[str] = Field(default = None, description = 'Title for the x-axis.')
    yaxis_title: Optional[str] = Field(default = None, description = 'Title for the y-axis.')
    height: Optional[int] = Field(default = None, description = 'Height of the chart in pixels.')
    width: Optional[int] = Field(default = None, description = 'Width of the chart in pixels.')
    
    measure_col: Optional[str] = Field(default = None, description = "Optional column defining waterfall measure ('relative', 'total', etc).")
    orientation: Literal['v', 'h'] = Field(default = 'v', description="Chart orientation: 'v' (vertical) or 'h' (horizontal).")
    title: Optional[str] = Field(default = 'Waterfall Chart', description = 'Title of the chart.')
    waterfall_gap: float = Field(default = 0.03, description = 'Gap between bars in the waterfall.')
    
    increasing: Optional[WaterfallMarkerStyle] = Field(default = None, description = 'Styling for increasing bars.')
    decreasing: Optional[WaterfallMarkerStyle] = Field(default = None, description = 'Styling for decreasing bars.')
    totals: Optional[WaterfallMarkerStyle] = Field(default = None, description = 'Styling for total bars.')
    connector: Optional[WaterfallConnectorStyle] = Field(default_factory = WaterfallConnectorStyle, description = 'Styling for bar connectors.')
    
    text_col: Optional[str] = Field(default = None, description = 'Optional column with labels for each bar.')
    text_position: Optional[str] = Field(default = 'auto', description = 'Position of text labels on bars.')
    
    showlegend: bool = Field(default = False, description = 'Whether to show the chart legend.')
    template: str = Field(default = 'plotly_white', description = 'Plotly template to use for styling.')
    paper_bgcolor: Optional[str] = Field(default = None, description = 'Background color of the chart paper.')
    plot_bgcolor: Optional[str] = Field(default = None, description = 'Background color of the chart plot.')
    font_family: Optional[str] = Field(default = None, description = 'Font family to use.')
    font_color: Optional[str] = Field(default = None, description = 'Font color to use.')

    preprocess_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = Field(default = None, description = 'Optional function to preprocess the DataFrame.')
    preprocess_fn_args: Optional[Dict[str, Any]] = Field(default_factory = dict, description = 'Arguments for the preprocessing function.')

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

def create_configurable_waterfall(df: pd.DataFrame, config: WaterfallConfig = WaterfallConfig) -> go.Figure:
    """
    Generates a fully customizable Plotly waterfall chart using WaterfallConfig.

    Args:
        df (pd.DataFrame): Input DataFrame with required x/y values and optional metadata.
        config (WaterfallConfig): Configuration object defining layout, style, and logic.

    Returns:
        go.Figure: Rendered Plotly waterfall chart.
    """
    df = df.copy()

    if config.preprocess_fn:
        try:
            df = config.preprocess_fn(df, **config.preprocess_fn_args)
        except Exception as e:
            raise RuntimeError(f"Failed to preprocess DataFrame: {e}")

    trace_kwargs = {
        'orientation': config.orientation,
        'x': df[config.x_col],
        'y': df[config.y_col],
    }

    trace_kwargs['connector'] = {
        'line': {
            'color': config.connector.color,
            **({'width': config.connector.width} if config.connector.width else {}),
            **({'dash': config.connector.dash} if config.connector.dash else {})
        }
    }

    if config.measure_col:
        trace_kwargs['measure'] = df[config.measure_col]
    if config.text_col:
        trace_kwargs['text'] = df[config.text_col]
        trace_kwargs['textposition'] = config.text_position

    if config.increasing:
        trace_kwargs['increasing'] = {
            'marker': {
                'color': config.increasing.color,
                'line': {
                    'color': config.increasing.line_color or config.increasing.color,
                    'width': config.increasing.line_width,
                },
            }
        }
    if config.decreasing:
        trace_kwargs['decreasing'] = {
            'marker': {
                'color': config.decreasing.color,
                'line': {
                    'color': config.decreasing.line_color or config.decreasing.color,
                    'width': config.decreasing.line_width,
                },
            }
        }
    if config.totals:
        trace_kwargs['totals'] = {
            'marker': {
                'color': config.totals.color,
                'line': {
                    'color': config.totals.line_color or config.totals.color,
                    'width': config.totals.line_width,
                },
            }
        }

    fig = go.Figure(go.Waterfall(**trace_kwargs))

    fig.update_layout(
        title = config.title,
        waterfallgap = config.waterfall_gap,
        showlegend = config.showlegend,
        template = config.template,
        paper_bgcolor = config.paper_bgcolor,
        plot_bgcolor = config.plot_bgcolor,
        font = dict(
            family = config.font_family,
            color = config.font_color
        ) if config.font_family or config.font_color else None
    )

    return fig
