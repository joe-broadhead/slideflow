import pandas as pd
import plotly.graph_objects as go
from typing import Any, Callable, Dict, Optional, Union, List
from pydantic import BaseModel, Field, root_validator

from slideflow.chart.builtins.common import BuiltinChartType, ChartConfig
from slideflow.utils.formatting.color import BUILTIN_COLOR_FUNCTIONS
from slideflow.utils.formatting.format import BUILTIN_FORMAT_FUNCTIONS

BUILTIN_FUNCTIONS = BUILTIN_COLOR_FUNCTIONS | BUILTIN_FORMAT_FUNCTIONS

class TableColumnFormatter(BaseModel):
    """
    Configuration for formatting and coloring individual columns in a table.

    This model allows users to specify a function for formatting the values in a column
    and an optional function for determining the text color of each value.

    Attributes:
        format_fn (Callable[[Any], str]): A function that formats a cell's value into a string.
        format_fn_args (Optional[Dict[str, Any]]): Additional keyword arguments passed to the formatting function.
        color_fn (Callable[[Any], str]): A function that returns a color name or hex code for a cell value.
        color_fn_args (Optional[Dict[str, Any]]): Additional keyword arguments passed to the color function.
    """
    format_fn: Callable[[Any], str]
    format_fn_args: Optional[Dict[str, Any]] = Field(default_factory = dict, description = 'Additional keyword arguments for the format function')
    color_fn: Callable[[Any], str] = Field(default = lambda x: 'black')
    color_fn_args: Optional[Dict[str, Any]] = Field(default_factory = dict, description = 'Additional keyword arguments for the color function')
    
    @root_validator(pre = True)
    def resolve_function_names(cls, values):
        """
        Resolves any string references to functions in the format_fn and color_fn fields 
        using the BUILTIN_FUNCTIONS registry.

        Args:
            values (dict): The dictionary of field values.

        Returns:
            dict: The updated field values with resolved function references.

        Raises:
            ValueError: If a provided function name is not found in BUILTIN_FUNCTIONS.
        """
        for key in ['format_fn', 'color_fn']:
            if isinstance(values.get(key), str):
                func_name = values[key]
                if func_name not in BUILTIN_FUNCTIONS:
                    raise ValueError(f'Unknown function: {func_name}')
                values[key] = BUILTIN_FUNCTIONS[func_name]
        return values

class TableFormattingOptions(BaseModel):
    """
    Configuration for customizing the formatting and coloring of table data.

    This model allows users to specify default formatting and color functions 
    for all columns, and override these behaviors for individual columns using 
    `custom_formatters`. An optional function for row-level highlighting is also supported.

    Attributes:
        default_format_fn (Callable[[Any], str]): 
            Default function to convert cell values to formatted strings. Defaults to `str(x)`.
        
        default_color_fn (Callable[[Any], str]): 
            Default function to determine the color of cell text. Defaults to `'black'`.

        custom_formatters (Dict[str, TableColumnFormatter]): 
            A dictionary mapping column names to custom formatter configurations. These 
            override the default formatting and coloring behavior for the specified columns.

        highlight_condition_fn (Optional[Callable[[pd.Series], bool]]): 
            An optional function that accepts a row (`pd.Series`) and returns `True` if 
            the row should be highlighted. Defaults to `None`.
    """
    default_format_fn: Callable[[Any], str] = Field(default = lambda x: str(x))
    default_color_fn: Callable[[Any], str] = Field(default = lambda x: 'black')
    custom_formatters: Dict[str, TableColumnFormatter] = Field(default_factory = dict)
    highlight_condition_fn: Optional[Callable[[pd.Series], bool]] = Field(default = None)

class TableHeaderConfig(BaseModel):
    """
    Configuration for the appearance of the table header.

    Controls styling properties such as fill color, font color, size, alignment, 
    and height of the table header.

    Attributes:
        fill_color (str): 
            Background color of the header row. Defaults to '#3643BA'.
        
        font_color (str): 
            Text color of the header. Defaults to 'white'.
        
        font_size (int): 
            Font size of the header text. Defaults to 12.
        
        align (str): 
            Horizontal alignment of header text. Common values are 'left', 'center', or 'right'. Defaults to 'center'.
        
        height (int): 
            Height of the header row in points. Defaults to 32.
    """
    fill_color: str = '#3643BA'
    font_color: str = 'white'
    font_size: int = 12
    align: Union[str, List[str]] = 'left'
    height: int = 32

class TableCellConfig(BaseModel):
    """
    Configuration for the appearance of individual table cells.

    Defines default styles and layout for cells in the table, including 
    font settings, alignment, row height, and background fill colors.

    Attributes:
        font_family (str): 
            Font family used for cell text. Defaults to 'Arial'.

        font_size (int): 
            Size of the text in table cells. Defaults to 12.

        align (str): 
            Horizontal alignment of the cell content. Common values are 
            'left', 'center', or 'right'. Defaults to 'left'.

        height (int): 
            Height of each row in the table, in points. Defaults to 26.

        default_fill (str): 
            Background color of regular cells. Defaults to 'white'.

        highlight_fill (str): 
            Background color for highlighted rows or cells. 
            Used when a highlight condition is met. Defaults to '#f2f2f2'.
    """
    font_family: str = 'Arial'
    font_size: int = 12
    align: Union[str, List[str]] = 'left'
    height: int = 26
    default_fill: str = 'white'
    highlight_fill: str = '#f2f2f2'

class TableLayoutConfig(BaseModel):
    """
    Configuration for the overall layout of a table.

    Specifies layout-related properties such as margins and height of the table.

    Attributes:
        margin (Dict[str, int]): 
            Dictionary specifying the margins around the table in points. 
            Keys include 'l' (left), 'r' (right), 't' (top), and 'b' (bottom). 
            Defaults to {'l': 0, 'r': 0, 't': 0, 'b': 0}.

        height (int): 
            Total height of the table in points. 
            This value may influence the scale or fitting of the table 
            in the slide layout. Defaults to 300.
    """
    margin: Dict[str, int] = Field(default_factory = lambda: {'l': 0, 'r': 0, 't': 0, 'b': 0})
    height: int = 300
    width: int = 800

class TableConfig(ChartConfig):
    """
    Configuration class for table charts.

    This class extends `ChartConfig` to support table-specific properties such
    as column mappings, layout, formatting, and preprocessing logic.

    Attributes:
        column_map (Dict[str, str]): 
            Mapping of internal column names to display names.
        columnwidth (Optional[list]): 
            Optional list of column widths.
        header (Optional[TableHeaderConfig]): 
            Configuration for table header appearance (e.g., font, color, height).
        cell (Optional[TableCellConfig]): 
            Configuration for table cell appearance (e.g., font, alignment).
        layout (Optional[TableLayoutConfig]): 
            Layout configuration for the entire table (e.g., margins, height).
        formatting (TableFormattingOptions): 
            Formatting options for table data, including formatting functions and color rules.
        preprocess_functions (List[Dict[str, Any]]):
            A list of preprocessing steps to apply to the data before rendering. Each step includes a function reference and optional arguments, allowing for filtering, grouping, or transforming the data prior to display.
    """
    chart_type: BuiltinChartType = Field('table', description = "Type of chart. Should be 'table'")
    column_map: Dict[str, str] = Field(..., description = 'Mapping from internal column names to display names.')
    columnwidth: Optional[list] = Field(default_factory = lambda: [])
    header: Optional[TableHeaderConfig] = Field(default_factory = TableHeaderConfig)
    cell: Optional[TableCellConfig] = Field(default_factory = TableCellConfig)
    layout: Optional[TableLayoutConfig] = Field(default_factory = TableLayoutConfig)
    formatting: TableFormattingOptions = Field(default_factory = TableFormattingOptions)
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

def create_configurable_table(df: pd.DataFrame, config: TableConfig = TableConfig) -> go.Figure:
    """
    Creates a Plotly table chart using the provided DataFrame and configuration.

    This function formats and styles a table chart using the settings defined
    in the `TableConfig`, including preprocessing, formatting functions,
    column mappings, highlighting, and visual layout.

    Args:
        df (pd.DataFrame): 
            The input DataFrame to visualize.
        config (TableConfig): 
            Configuration for table appearance, formatting, and preprocessing. 
            Defaults to an empty `TableConfig` instance.

    Returns:
        go.Figure: 
            A Plotly figure object representing the styled table chart.

    Raises:
        RuntimeError: 
            If the `preprocess_fn` is provided but fails to execute with the specified arguments.
    """
    df = df.copy()

    if config.preprocess_functions:
        for step in config.preprocess_functions:
            fn_name = step["function"]
            args = step.get("args", {})
            df = fn_name(df, **args)

    cols = list(config.column_map.keys())
    df = df[cols]
    num_rows = len(df)

    if config.formatting.highlight_condition_fn:
        highlight_rows = df.apply(config.formatting.highlight_condition_fn, axis = 1)
    else:
        highlight_rows = [False] * num_rows

    cell_values = []
    font_colors = []
    fills = []
    
    for col in cols:
        formatter = config.formatting.custom_formatters.get(
            col,
            TableColumnFormatter(
                format_fn = config.formatting.default_format_fn,
                color_fn = config.formatting.default_color_fn
            )
        )
        
        col_values = []
        col_colors = []
        col_fills = []

        for i in range(num_rows):
            raw_val = df[col].iloc[i]
            formatted_val = formatter.format_fn(raw_val, **formatter.format_fn_args)
            col_values.append(formatted_val)
            col_colors.append(formatter.color_fn(raw_val, **formatter.color_fn_args))
            # Set background fill based on highlight condition.
            if hasattr(highlight_rows, 'iloc'):
                highlight = highlight_rows.iloc[i]
            else:
                highlight = highlight_rows[i]
            col_fills.append(config.cell.highlight_fill if highlight else config.cell.default_fill)
        cell_values.append(col_values)
        font_colors.append(col_colors)
        fills.append(col_fills)

    fig = go.Figure(
        data = [
            go.Table(
                columnwidth = config.columnwidth,
                header = dict(
                    values = [f'<b>{config.column_map[col]}</b>' for col in cols],
                    fill_color = config.header.fill_color,
                    font = dict(color = config.header.font_color, size = config.header.font_size),
                    align = config.header.align,
                    height = config.header.height
                ),
                cells = dict(
                    values = cell_values,
                    fill = dict(color = fills),
                    font = dict(color = font_colors, family = config.cell.font_family, size = config.cell.font_size),
                    align = config.cell.align,
                    height = config.cell.height
                )
            )
        ]
    )
    
    fig.update_layout(margin = config.layout.margin, height = config.layout.height, width = config.layout.width)

    return fig
