from enum import Enum
from pydantic import BaseModel, Field

class BuiltinChartType(str, Enum):
    """
    Enumeration of built-in chart types supported by Slideflow.

    Attributes:
        table (str): A table-style chart.
        bar (str): A horizontal or vertical bar chart.
    """
    table = 'table'
    bar = 'bar'
    waterfall = 'waterfall'
    line = 'line'

class ChartConfig(BaseModel):
    """
    Base configuration class for any chart.

    This class defines the required structure for identifying 
    the type of chart being configured. It is intended to be subclassed 
    by specific chart configuration models such as BarChartConfig or TableConfig.

    Attributes:
        chart_type (str): 
            A string identifying the chart type (e.g., 'bar', 'table').
    """
    chart_type: BuiltinChartType = Field(..., description = "Type of chart. Should be one of 'BuiltinChartType'")
    
    def resolve_args(self, params: dict[str, str]) -> None:
        raise NotImplementedError('Subclasses must implement resolve_args().')
