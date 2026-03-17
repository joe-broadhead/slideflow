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
    - Automatic image generation for provider-managed upload/insertion

Architecture:
    All charts inherit from BaseChart and implement the generate_chart_image method.
    Charts can fetch data from configured data sources, apply transformations, and
    generate images that are uploaded by the active presentation provider.

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
    >>> # Generate chart image bytes; provider handles upload/insertion
    >>> image_bytes = chart.generate_chart_image(chart.fetch_data())
"""

import atexit
import re
import uuid
import warnings
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor, TimeoutError
try:
    from concurrent.futures import BrokenProcessPool  # type: ignore[attr-defined]
except ImportError:
    from concurrent.futures.process import BrokenProcessPool  # type: ignore[assignment]
from threading import Lock
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Union

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from pydantic import BaseModel, ConfigDict, Field, field_validator

from slideflow.builtins.template_engine import get_template_engine
from slideflow.constants import GoogleSlides, Timing
from slideflow.data.connectors.base import BaseSourceConfig as DataSourceConfig
from slideflow.presentations.positioning import safe_eval_expression
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.utilities.exceptions import ChartGenerationError
from slideflow.utilities.logging import get_logger

# Suppress known noisy dependency warnings that can interfere with process execution
# or be incorrectly treated as errors in some environments.
warnings.filterwarnings("ignore", message=".*urllib3.*match a supported version.*")
try:
    # Some versions of requests define this specific warning class
    from requests import RequestsDependencyWarning  # type: ignore

    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
except ImportError:
    pass

logger = get_logger(__name__)
_LIST_COLUMN_REF_PATTERN = re.compile(r"^\$([a-zA-Z_]\w*)(?:\[(-?\d+)\])?$")

_CHART_EXPORT_EXECUTOR: Optional[ProcessPoolExecutor] = None
_CHART_EXPORT_EXECUTOR_LOCK = Lock()


def _initialize_chart_export_worker() -> None:
    """Prepare worker process for chart generation.

    Includes workarounds for upstream library issues (like Kaleido #402).
    This function runs once per worker process creation.
    """
    try:
        # Suppress noisy dependency warnings in worker
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import kaleido  # type: ignore[import-untyped]
            import plotly.io as pio

            # Workaround for plotly/Kaleido#402 to prevent random hangs on export.
            # Disabling MathJax prevents the browser from hanging while fetching CDNs.
            if hasattr(pio.kaleido, "scope"):
                pio.kaleido.scope.mathjax = None

            # This initializes the internal Chromium engine.
            if hasattr(kaleido, "get_chrome_sync"):
                kaleido.get_chrome_sync()
    except Exception as error:
        # Avoid crashing worker during initialization; fall back to normal execution.
        logger.debug("Kaleido worker initialization failed: %s", error, exc_info=True)


def _get_chart_export_executor() -> ProcessPoolExecutor:
    global _CHART_EXPORT_EXECUTOR
    with _CHART_EXPORT_EXECUTOR_LOCK:
        if _CHART_EXPORT_EXECUTOR is None:
            _CHART_EXPORT_EXECUTOR = ProcessPoolExecutor(
                max_workers=1, initializer=_initialize_chart_export_worker
            )
        return _CHART_EXPORT_EXECUTOR


def _reset_chart_export_executor() -> None:
    global _CHART_EXPORT_EXECUTOR
    with _CHART_EXPORT_EXECUTOR_LOCK:
        executor = _CHART_EXPORT_EXECUTOR
        _CHART_EXPORT_EXECUTOR = None

    if executor is None:
        return

    # Best effort teardown: terminate worker process to avoid hanging exports.
    try:
        for process in getattr(executor, "_processes", {}).values():
            process.terminate()
    except Exception as error:
        logger.debug("Chart export worker teardown failed: %s", error, exc_info=True)

    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception as error:
        logger.debug("Chart export executor shutdown failed: %s", error, exc_info=True)


def _shutdown_chart_export_executor() -> None:
    _reset_chart_export_executor()


atexit.register(_shutdown_chart_export_executor)


def _plotly_to_image(
    fig: go.Figure, fmt: str, width: int, height: int, scale: Optional[float]
) -> bytes:
    """Render a Plotly figure to bytes with explicit headless Kaleido defaults.

    Falls back to Plotly's standard exporter if direct Kaleido invocation fails.
    This keeps behavior robust across local desktops and headless orchestrators.
    """
    opts: Dict[str, Any] = {
        "format": fmt,
        "width": width,
        "height": height,
    }
    if scale is not None:
        opts["scale"] = scale

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import kaleido  # type: ignore[import-untyped]

            # Ensure MathJax is disabled in the main process too.
            if hasattr(pio.kaleido, "scope"):
                pio.kaleido.scope.mathjax = None

            # Reuse a single sync server per process to avoid repeatedly spawning
            # browser processes for each chart export.
            kaleido.start_sync_server(
                n=1,
                timeout=Timing.CHART_EXPORT_KALEIDO_START_TIMEOUT_S,
                headless=True,
                silence_warnings=True,
            )

            # Force headless browser execution so local desktop runs avoid visible windows
            # and orchestrated runs remain deterministic.
            return kaleido.calc_fig_sync(fig.to_plotly_json(), opts=opts)
    except Exception:
        logger.debug(
            "Direct Kaleido export failed; falling back to plotly.io.to_image.",
            exc_info=True,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Ensure MathJax is disabled before falling back.
            if hasattr(pio.kaleido, "scope"):
                pio.kaleido.scope.mathjax = None
            return pio.to_image(
                fig,
                format=fmt,
                width=width,
                height=height,
                scale=scale,
            )


def _execute_with_retry(func, *args, **kwargs):
    """
    Executes a function with a retry mechanism.

    The timeout sequence is configured via ``Timing.CHART_EXPORT_RETRY_TIMEOUTS_S``.
    If execution times out, the chart export worker is reset before retrying.
    If all retries are exhausted, raises ChartGenerationError.
    """
    execution_id = uuid.uuid4().hex[:8]
    timeouts = Timing.CHART_EXPORT_RETRY_TIMEOUTS_S
    for i, timeout in enumerate(timeouts):
        executor = _get_chart_export_executor()
        try:
            logger.info(
                "[%s] Attempting execution of %s (Attempt %s/%s, timeout=%ss)",
                execution_id,
                func.__name__,
                i + 1,
                len(timeouts),
                timeout,
            )
            future = executor.submit(func, *args, **kwargs)
            result = future.result(timeout=timeout)
            logger.info(
                "[%s] Execution of %s completed successfully",
                execution_id,
                func.__name__,
            )
            return result
        except (TimeoutError, BrokenProcessPool) as error:
            # Reset the worker on timeout or process crash to clear stuck/broken state.
            _reset_chart_export_executor()

            error_type = type(error).__name__
            logger.warning(
                "[%s] Function %s failed with %s. Retrying... Attempt %s of %s",
                execution_id,
                func.__name__,
                error_type,
                i + 1,
                len(timeouts),
            )
            continue
        except RuntimeError as error:
            # Catching RuntimeError handles cases where the executor was shut down
            # by a parallel task resetting it. Only retry if it's a shutdown error.
            _reset_chart_export_executor()
            if "cannot schedule new futures" in str(error):
                logger.warning(
                    "[%s] Function %s failed because executor was shut down. Retrying... Attempt %s of %s",
                    execution_id,
                    func.__name__,
                    i + 1,
                    len(timeouts),
                )
                continue
            raise
        except Exception as e:
            # We catch generic exceptions to ensure we reset the executor on unexpected crashes.
            # Logging exc_info here ensures we see the EXACT error (e.g. ValueError from Kaleido)
            # rather than just the generic "failed after all retries" wrapper.
            logger.error(
                "[%s] Unexpected error in worker during %s: %s",
                execution_id,
                func.__name__,
                type(e).__name__,
                exc_info=True,
            )
            _reset_chart_export_executor()
            raise
    raise ChartGenerationError(
        f"[{execution_id}] Function {func.__name__} failed after all retries."
    )


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
    - Presentation providers for upload/insertion

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

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    type: Annotated[str, Field(..., description="Chart type discriminator")]
    title: Annotated[Optional[str], Field(None, description="Chart title")]
    data_source: Annotated[
        Optional[DataSourceConfig], Field(None, description="Data source configuration")
    ]
    data_transforms: Annotated[
        Optional[List[Dict[str, Any]]],
        Field(
            None, description="Optional data transformations (resolved by ConfigLoader)"
        ),
    ]

    # Chart positioning and sizing (supports expressions and different units)
    width: Annotated[
        Union[float, str],
        Field(400, description="Chart width (supports expressions like '400 + 50')"),
    ]
    height: Annotated[
        Union[float, str], Field(300, description="Chart height (supports expressions)")
    ]
    x: Annotated[
        Union[float, str], Field(50, description="X position (supports expressions)")
    ]
    y: Annotated[
        Union[float, str], Field(50, description="Y position (supports expressions)")
    ]
    dimensions_format: Annotated[
        str,
        Field(
            "pt",
            description="Dimension format: 'pt', 'emu', 'relative', or 'expression'",
        ),
    ]
    alignment_format: Annotated[
        Optional[str],
        Field(None, description="Alignment format like 'center-top', 'left-bottom'"),
    ]
    scale: Annotated[
        Optional[float],
        Field(2.0, description="Image scaling factor for higher resolution"),
    ]

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
            raise ChartGenerationError(
                f"dimensions_format must be 'pt', 'emu', 'relative', or 'expression', got: {v}"
            )
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

        if "-" not in v:
            raise ChartGenerationError(
                f"alignment_format must be 'horizontal-vertical', got: {v}"
            )

        horizontal, vertical = v.split("-")
        if horizontal not in ("left", "center", "right"):
            raise ChartGenerationError(
                f"horizontal alignment must be 'left', 'center', or 'right', got: {horizontal}"
            )
        if vertical not in ("top", "center", "bottom"):
            raise ChartGenerationError(
                f"vertical alignment must be 'top', 'center', or 'bottom', got: {vertical}"
            )

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
        raise NotImplementedError


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
    traces: Annotated[
        List[Dict[str, Any]], Field(..., description="List of trace configurations")
    ]
    layout_config: Annotated[
        Optional[Dict[str, Any]], Field(None, description="Plotly layout configuration")
    ]

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
            trace_type = trace_config_copy.pop("type")  # e.g., 'scatter', 'bar'
            trace_class = getattr(go, trace_type.title())  # go.Scatter, go.Bar

            # Replace column references with actual data
            processed_config = self._process_trace_config(
                trace_config_copy, transformed_df
            )

            fig.add_trace(trace_class(**processed_config))

        if self.layout_config:
            fig.update_layout(**self.layout_config)

        if self.title and (not self.layout_config or "title" not in self.layout_config):
            fig.update_layout(title=self.title)

        # Evaluate width and height if they are expressions
        chart_width = (
            safe_eval_expression(self.width)
            if isinstance(self.width, str)
            else self.width
        )
        chart_height = (
            safe_eval_expression(self.height)
            if isinstance(self.height, str)
            else self.height
        )

        # Convert from points (72 DPI) to pixels (96 DPI) for Plotly
        # Google Slides uses points as its unit (72 DPI), but Plotly's to_image expects pixels at 96 DPI
        # Conversion factor ensures the chart appears at the correct size in slides
        POINTS_TO_PIXELS = GoogleSlides.POINTS_TO_PIXELS_RATIO
        image_width = int(chart_width * POINTS_TO_PIXELS)
        image_height = int(chart_height * POINTS_TO_PIXELS)

        return _execute_with_retry(
            _plotly_to_image,
            fig,
            "png",
            image_width,
            image_height,
            self.scale,
        )

    @staticmethod
    def _series_to_values(series: Any) -> List[Any]:
        """Normalize pandas-like series data into list values."""
        if hasattr(series, "tolist"):
            return series.tolist()
        return list(series)

    @staticmethod
    def _parse_direct_reference(raw_reference: str) -> tuple[str, Optional[int]]:
        """Parse direct `$column` / `$column[index]` trace references."""
        column_name = raw_reference
        index_token: Optional[int] = None
        if raw_reference.endswith("]") and "[" in raw_reference:
            potential_column, potential_index = raw_reference.rsplit("[", 1)
            potential_index = potential_index[:-1]
            if potential_column:
                try:
                    parsed_index = int(potential_index)
                except ValueError:
                    parsed_index = None
                if parsed_index is not None:
                    column_name = potential_column
                    index_token = parsed_index
        return column_name, index_token

    def _resolve_direct_trace_value(
        self, reference: str, df: pd.DataFrame, has_rows: bool
    ) -> tuple[bool, Any]:
        """Resolve direct `$column` references used in dict trace values."""
        column_name, index_token = self._parse_direct_reference(reference)

        if has_rows and column_name in df.columns:
            values = self._series_to_values(df[column_name])
            if index_token is None:
                return True, values
            try:
                return True, values[index_token]
            except IndexError as exc:
                raise ChartGenerationError(
                    f"Index {index_token} out of range for column '{column_name}' "
                    f"with {len(values)} row(s)."
                ) from exc

        if not has_rows:
            # For static charts without data, skip direct column references.
            return False, None

        available_columns = list(df.columns)
        df_shape = getattr(df, "shape", (len(df), len(df.columns)))
        raise ChartGenerationError(
            f"Column '{column_name}' not found in PlotlyGraphObjects trace config. "
            f"Available columns: {available_columns}. "
            f"DataFrame shape: {df_shape}"
        )

    def _resolve_list_trace_item(
        self, item: Any, df: pd.DataFrame, has_rows: bool
    ) -> Any:
        """Resolve list item references used in trace list values."""
        if not isinstance(item, str):
            return item

        match = _LIST_COLUMN_REF_PATTERN.match(item)
        if not match:
            return item

        column_name = match.group(1)
        list_index_token = match.group(2)

        if has_rows and column_name in df.columns:
            values = self._series_to_values(df[column_name])
            if list_index_token is None:
                return values
            index_value = int(list_index_token)
            try:
                return values[index_value]
            except IndexError as exc:
                raise ChartGenerationError(
                    f"Index {index_value} out of range for column '{column_name}' "
                    f"with {len(values)} row(s)."
                ) from exc

        if not has_rows:
            # Preserve list structure for Plotly table configs.
            if list_index_token is None:
                return []
            return None

        # Unresolvable list references are preserved literally.
        return item

    def _process_trace_config(
        self, config: Dict[str, Any], df: pd.DataFrame
    ) -> Dict[str, Any]:
        """Process trace configuration by replacing column references with data."""
        processed: Dict[str, Any] = {}
        has_rows = len(df) > 0

        for key, value in config.items():
            if isinstance(value, str) and value.startswith("$") and "%{" not in value:
                handled, resolved = self._resolve_direct_trace_value(
                    value[1:], df, has_rows
                )
                if handled:
                    processed[key] = resolved
                continue

            if isinstance(value, dict):
                processed[key] = self._process_trace_config(value, df)
                continue

            if isinstance(value, list):
                processed[key] = [
                    self._resolve_list_trace_item(item, df, has_rows) for item in value
                ]
                continue

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
    chart_fn: Annotated[
        Callable, Field(..., description="Chart function resolved by ConfigLoader")
    ]
    chart_config: Annotated[
        Dict[str, Any],
        Field(
            default_factory=dict, description="Configuration for the custom function"
        ),
    ]

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

        processed_config["title"] = self.title

        return chart_func(transformed_df, processed_config, self)

    def _process_config(
        self, config: Dict[str, Any], df: pd.DataFrame
    ) -> Dict[str, Any]:
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
        processed: Dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, str) and value.startswith("$"):
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
                    (
                        df[item[1:]]
                        if isinstance(item, str)
                        and item.startswith("$")
                        and item[1:] in df.columns
                        else item
                    )
                    for item in value
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
    template_name: Annotated[
        str, Field(..., description="Name of the YAML template to use")
    ]
    template_config: Annotated[
        Dict[str, Any],
        Field(default_factory=dict, description="Configuration for the template"),
    ]

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
        rendered_config = engine.render_template(
            self.template_name, self.template_config
        )

        # Create a PlotlyGraphObjects chart with the rendered config
        # Combine user transforms with template transforms
        all_transforms = (self.data_transforms or []) + (
            rendered_config.get("data_transforms", [])
        )

        plotly_chart = PlotlyGraphObjects(
            type="plotly_go",
            title=self.title,
            data_source=None,  # We already have the data
            data_transforms=all_transforms,
            traces=rendered_config["traces"],
            layout_config=rendered_config.get("layout_config", {}),
            width=self.width,
            height=self.height,
            x=self.x,
            y=self.y,
            dimensions_format=self.dimensions_format,
            alignment_format=self.alignment_format,
            scale=self.scale,
        )

        return plotly_chart.generate_chart_image(df)


ChartUnion = Annotated[
    Union[PlotlyGraphObjects, CustomChart, TemplateChart], Field(discriminator="type")
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
