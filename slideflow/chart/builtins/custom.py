from pydantic import Field
from typing import Any, Dict, List

from slideflow.chart.builtins.common import BuiltinChartType, ChartConfig

class CustomChartConfig(ChartConfig):
    chart_type: BuiltinChartType = Field('custom', description = "Type of chart. Should be 'custom'") 
    preprocess_functions: List[Dict[str, Any]] = Field(default_factory = list)

    def resolve_args(self, params: dict[str, str]) -> None:
        """
        Updates all preprocess function args by formatting any string values with the provided params.

        Args:
            params (dict[str, str]): Parameters to use for string interpolation.
        """
        if hasattr(self, 'preprocess_functions'):
            for step in self.preprocess_functions:
                if 'args' in step:
                    for k, v in step['args'].items():
                        if isinstance(v, str):
                            step['args'][k] = v.format(**params)
