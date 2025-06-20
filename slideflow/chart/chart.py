import uuid
from typing import Union, Callable, Any, Optional, Tuple, Annotated
from pydantic import BaseModel, Field, field_validator, model_validator

from slideflow.data.data_manager import DataManager
from slideflow.data.connectors.base import DataSourceConfig
from slideflow.chart.builtins.common import BuiltinChartType
from slideflow.chart.builtins.custom import CustomChartConfig
from slideflow.chart.utils import generate_figure_image, upload_image_to_drive
from slideflow.chart.builtins.bar import BarChartConfig, create_configurable_bar
from slideflow.chart.builtins.table import TableConfig, create_configurable_table
from slideflow.chart.builtins.line import LineChartConfig, create_configurable_line
from slideflow.chart.builtins.waterfall import WaterfallConfig, create_configurable_waterfall
from slideflow.chart.builtins.grouped_bar import GroupedBarChartConfig, create_configurable_grouped_bar
from slideflow.chart.builtins.combo_chart import ComboChartConfig, create_configurable_combo_chart

BUILT_IN_CHARTS = {
    'table': create_configurable_table,
    'bar': create_configurable_bar,
    'waterfall': create_configurable_waterfall,
    'line': create_configurable_line,
    'grouped_bar': create_configurable_grouped_bar,
    'combo_chart': create_configurable_combo_chart
}

CHART_CONFIGS = [
    TableConfig,
    BarChartConfig,
    WaterfallConfig,
    LineChartConfig,
    GroupedBarChartConfig,
    ComboChartConfig,
    CustomChartConfig
]

class Chart(BaseModel):
    """
    Represents a chart to be inserted into a Google Slide.

    This model includes chart metadata, layout configuration, a chart rendering
    function (built-in or custom), and a reference to the underlying data source.

    Attributes:
        object_id (str): Unique identifier for the chart object on the slide.
        name (str): Human-readable name for the chart.
        chart_function (Union[BuiltinChartType, Callable[[Any], Any]]): A built-in chart type 
            (e.g. 'bar', 'table') or a custom rendering function.
        chart_config (Optional[Union[TableConfig, BarChartConfig]]): Optional configuration
            used by the chart rendering function (e.g. axis labels, styles).
        data_source (DataSourceConfig): The source of the data to be visualized.
        width (Union[float, str]): Width of the chart. Can be a numeric value or a string expression.
        height (Union[float, str]): Height of the chart. Can be a numeric value or a string expression.
        x (Union[float, str]): Horizontal position of the chart on the slide.
        y (Union[float, str]): Vertical position of the chart on the slide.
        dimensions_format (str): Format of the chart dimensions. Options: 'pt', 'emu', or 'relative'.
        alignment (str): Anchor point for the chart positioning. 
            Options: 'left-top', 'center-center', 'right-bottom', etc.
    """
    object_id: str = Field(
        default_factory = lambda: str(uuid.uuid4()),
        description = 'Unique identifier for the chart object'
    )
    name: str = Field(..., description = 'Name of the chart')
    chart_function: Annotated[
        Union[BuiltinChartType, Callable[[Any], Any]],
        Field(description = 'Either a built-in chart type or a custom function.')
    ]
    chart_config: Optional[Union[*CHART_CONFIGS]] = Field(
        None, description = 'Optional configuration for the chart type'
    )
    data_source: DataSourceConfig = Field(..., description = 'Data source to be visualized')
    width: Union[float, str] = Field(0, description = 'Chart width (can be absolute or relative)')
    height: Union[float, str] = Field(0, description = 'Chart height (can be absolute or relative)')
    x: Union[float, str] = Field(0, description = 'X coordinate of chart')
    y: Union[float, str] = Field(0, description = 'Y coordinate of chart')
    dimensions_format: str = Field('pt', description = 'Unit for chart dimensions: pt, emu, or relative')
    alignment: str = Field('left-top', description = 'Chart alignment on the slide')

    @field_validator('dimensions_format')
    @classmethod
    def check_dimensions_format(cls, value: str) -> str:
        """
        Validates the `dimensions_format` field to ensure it is one of the supported formats.

        Args:
            value (str): The dimensions format string to validate.

        Returns:
            str: The validated dimensions format string.

        Raises:
            ValueError: If the format is not one of 'pt', 'emu', or 'relative'.
        """
        if value not in {'pt', 'emu', 'relative'}:
            raise ValueError("dimensions_format must be one of: 'pt', 'emu', 'relative'")
        return value

    @field_validator('alignment')
    @classmethod
    def check_alignment(cls, value: str) -> str:
        """
        Validates the `alignment` field to ensure it is one of the accepted alignment strings.

        Args:
            value (str): The alignment value to validate.

        Returns:
            str: The validated alignment string.

        Raises:
            ValueError: If the alignment is not one of the accepted values.
        """
        valid_alignments = {
            'left-top', 'left-center', 'left-bottom',
            'center-top', 'center-center', 'center-bottom',
            'right-top', 'right-center', 'right-bottom'
        }
        if value not in valid_alignments:
            raise ValueError(f"alignment must be one of: {', '.join(valid_alignments)}")
        return value

    @model_validator(mode = 'after')
    def check_config_matches_function(self):
        """
        Ensures that the chart configuration type matches the built-in chart function type.

        Returns:
            Chart: The validated Chart instance.

        Raises:
            ValueError: If the `chart_function` is a built-in type but the corresponding
                        `chart_config` is not of the expected type (`TableConfig` or `BarChartConfig`).
        """
        if isinstance(self.chart_function, BuiltinChartType):
            if self.chart_function == BuiltinChartType.table and not isinstance(self.chart_config, (type(None), TableConfig)):
                raise ValueError("If chart_function is 'table', chart_config must be TableConfig or None.")
            if self.chart_function == BuiltinChartType.bar and not isinstance(self.chart_config, (type(None), BarChartConfig)):
                raise ValueError("If chart_function is 'bar', chart_config must be BarChartConfig or None.")
        return self

    @property
    def chart_callable(self) -> Callable[[Any], Any]:
        """
        Resolves the chart function into a callable.

        If the chart function is a string referencing a built-in chart type (e.g., "bar", "table"),
        it looks up the corresponding function from the built-in chart registry.
        If it's already a callable, it is returned as is.

        Returns:
            Callable[[Any], Any]: A function that generates a chart based on input data.

        Raises:
            ValueError: If the string chart function does not match any known built-in chart type.
        """
        if isinstance(self.chart_function, str):
            chart_func = BUILT_IN_CHARTS.get(self.chart_function)
            if not chart_func:
                raise ValueError(f'Unknown built-in chart type: {self.chart_function}')
            return chart_func
        return self.chart_function

    def generate_chart_image(
        self,
        data_manager: DataManager,
        drive_service: Any
    ) -> Tuple[str, str]:
        """
        Generates a chart image from the data and uploads it to Google Drive.

        This method fetches data from the specified data source, renders a chart using
        the configured chart function and settings, generates an image from the chart,
        uploads the image to Google Drive, and returns its file ID and public URL.

        Args:
            data_manager (DataManager): The data manager used to load the data.
            drive_service (Any): An authenticated Google Drive API service client.

        Returns:
            Tuple[str, str]: A tuple containing the file ID and public URL of the uploaded image.
        """
        data = data_manager.get_data(self.data_source)
        chart_func = self.chart_callable

        if self.chart_config:
            fig = chart_func(data, self.chart_config)
        else:
            fig = chart_func(data)

        image_buf = generate_figure_image(fig, self.width, self.height)
        file_id, public_url = upload_image_to_drive(
            drive_service,
            image_buf,
            name = f'{self.object_id}.png'
        )
        return file_id, public_url
