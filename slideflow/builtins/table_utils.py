"""Table formatting and styling utilities for presentations.

This module provides advanced table formatting capabilities, particularly focused
on dynamic color mapping for data visualization in presentation tables. It includes
high-order functions that apply color schemes based on data values, making it easy
to create visually informative tables that highlight key metrics and trends.

The module is designed to work seamlessly with Plotly tables and Slideflow's
table replacement system, generating color columns that can be referenced in
YAML configurations.

Key Features:
    - Dynamic color mapping based on data values
    - Pre-built color functions for common scenarios (growth, performance)
    - Traffic light color schemes for multi-threshold visualization
    - Integration with Plotly table color arrays
    - Column-specific color application

Functions:
    create_dynamic_colors: Apply color functions to specific columns
    growth_color_function: Green/red coloring for positive/negative values
    performance_color_function: Threshold-based binary coloring
    create_traffic_light_colors: Three-tier color scheme (green/yellow/red)
    create_growth_colors: Convenience wrapper for growth coloring
    create_performance_colors: Convenience wrapper for performance coloring

Example:
    >>> import pandas as pd
    >>> from slideflow.builtins.table_utils import create_growth_colors
    >>> 
    >>> df = pd.DataFrame({
    ...     'product': ['A', 'B', 'C'],
    ...     'revenue': [100, 200, 150],
    ...     'growth': [0.15, -0.05, 0.10]
    ... })
    >>> 
    >>> # Apply growth colors
    >>> df_colored = create_growth_colors(
    ...     df,
    ...     column_order=['product', 'revenue', 'growth'],
    ...     growth_columns=['growth']
    ... )
    >>> 
    >>> # Color columns are now available as $_color_col_0, $_color_col_1, etc.
"""

import pandas as pd
from typing import List, Callable, Any

def create_dynamic_colors(
    df: pd.DataFrame, 
    column_order: List[str], 
    color_func: Callable[[Any], str], 
    target_columns: List[str]
) -> pd.DataFrame:
    """Create dynamic color arrays for table visualization.
    
    This high-order function applies a color mapping function to specified columns
    and generates color arrays that can be used in Plotly table configurations.
    It creates individual color columns for each table column, allowing fine-grained
    control over cell coloring based on data values.
    
    The function is particularly useful for creating tables where certain columns
    need to be highlighted based on their values (e.g., positive/negative growth,
    performance thresholds, status indicators).
    
    Args:
        df: DataFrame containing the table data. Original DataFrame is not modified.
        column_order: List of column names in the exact order they appear in the
            table. This must match the table's column configuration.
        color_func: A callable that takes a single value and returns a color string.
            Should handle edge cases (None, NaN, non-numeric) gracefully.
            Common formats: hex colors ('#RRGGBB'), named colors ('red'), 
            or rgba strings.
        target_columns: List of column names that should have the color function
            applied. Columns not in this list will use default color (black).
            Non-existent columns are silently ignored.
        
    Returns:
        New DataFrame with original data plus color columns. Color columns are
        named '_color_col_0', '_color_col_1', etc., corresponding to positions
        in column_order. These can be referenced in Plotly as $_color_col_N.
        
    Example:
        >>> # Define a growth coloring function
        >>> def growth_colors(value):
        ...     try:
        ...         return '#28a745' if float(value) >= 0 else '#dc3545'
        ...     except:
        ...         return 'gray'
        ... 
        >>> # Apply to specific columns
        >>> df_colored = create_dynamic_colors(
        ...     df, 
        ...     column_order=['name', 'revenue', 'growth', 'margin'],
        ...     color_func=growth_colors,
        ...     target_columns=['growth', 'margin']
        ... )
        >>> 
        >>> # In YAML configuration:
        >>> # charts:
        >>> #   - type: plotly_go
        >>> #     config:
        >>> #       traces:
        >>> #         - type: Table
        >>> #           cells:
        >>> #             values: [$name, $revenue, $growth, $margin]
        >>> #             font:
        >>> #               color: [$_color_col_0, $_color_col_1, 
        >>> #                       $_color_col_2, $_color_col_3]
        
    Note:
        - Color columns are prefixed with underscore to avoid conflicts
        - Column order must exactly match the table's column configuration
        - The color function should be deterministic for consistent results
        - Non-target columns receive 'black' as their color value
    """
    df = df.copy()
    
    colors = []
    
    for col in column_order:
        if col in target_columns and col in df.columns:
            # Apply the color function to each value in the target column
            col_colors = [color_func(val) for val in df[col]]
        else:
            # For non-target columns, use black
            col_colors = ['black'] * len(df)
        colors.append(col_colors)
    
    # Store individual color columns for each table column
    for i, col_colors in enumerate(colors):
        df[f'_color_col_{i}'] = col_colors
    
    return df

def growth_color_function(value: Any) -> str:
    """Color function for growth/change values using green/red scheme.
    
    A pre-built color function that maps numeric values to colors based on
    their sign. Positive values (including zero) are colored green to indicate
    growth or positive change, while negative values are colored red to indicate
    decline or negative change.
    
    This function is commonly used for:
        - Growth rates and percentages
        - Year-over-year changes
        - Performance deltas
        - Profit/loss indicators
    
    Args:
        value: The value to evaluate. Can be:
            - int or float: Numeric values are evaluated normally
            - str: Attempted conversion to float
            - None, NaN, or non-numeric: Returns 'black'
        
    Returns:
        Color string:
            - '#28a745' (green): For values >= 0
            - '#dc3545' (red): For values < 0  
            - 'black': For non-numeric or invalid values
            
    Example:
        >>> growth_color_function(15.5)
        '#28a745'
        
        >>> growth_color_function(-3.2)
        '#dc3545'
        
        >>> growth_color_function(0)
        '#28a745'
        
        >>> growth_color_function('N/A')
        'black'
        
    Note:
        - Zero is considered positive (returns green)
        - Uses Bootstrap color palette for consistency
        - Handles type conversion errors gracefully
    """
    try:
        return '#28a745' if float(value) >= 0 else '#dc3545'
    except (ValueError, TypeError):
        return 'black'

def performance_color_function(value: Any, threshold: float = 0.0) -> str:
    """Color function for performance metrics with configurable threshold.
    
    Maps values to colors based on whether they meet or exceed a performance
    threshold. This is useful for KPIs, targets, benchmarks, or any metric
    where there's a clear performance cutoff.
    
    Args:
        value: The numeric value to evaluate. Can be:
            - int or float: Compared against threshold
            - str: Attempted conversion to float
            - None, NaN, or non-numeric: Returns 'black'
        threshold: The minimum value to be considered "good" performance.
            Values >= threshold return green, values < threshold return red.
            Defaults to 0.0.
        
    Returns:
        Color string:
            - '#28a745' (green): For values >= threshold
            - '#dc3545' (red): For values < threshold
            - 'black': For non-numeric or invalid values
            
    Example:
        >>> # Default threshold of 0
        >>> performance_color_function(10)
        '#28a745'
        
        >>> performance_color_function(-5)
        '#dc3545'
        
        >>> # Custom threshold
        >>> performance_color_function(85, threshold=90)
        '#dc3545'
        
        >>> performance_color_function(95, threshold=90) 
        '#28a745'
        
        >>> # Invalid input
        >>> performance_color_function('N/A', threshold=50)
        'black'
        
    Note:
        - Threshold is inclusive (>= for green)
        - Useful for target-based metrics
        - Can be partially applied for use with create_dynamic_colors
    """
    try:
        return '#28a745' if float(value) >= threshold else '#dc3545'
    except (ValueError, TypeError):
        return 'black'

def create_traffic_light_colors(
    value: Any, 
    good_threshold: float, 
    warning_threshold: float
) -> str:
    """Three-tier color function using traffic light scheme.
    
    Maps values to green, yellow, or red based on two thresholds, creating
    a traffic light visualization. This is ideal for metrics with multiple
    performance levels or risk indicators.
    
    Common use cases:
        - Risk assessment (low/medium/high)
        - Performance tiers (excellent/acceptable/poor)
        - Health metrics (healthy/warning/critical)
        - SLA compliance levels
    
    Args:
        value: The numeric value to evaluate. Can be:
            - int or float: Compared against both thresholds
            - str: Attempted conversion to float
            - None, NaN, or non-numeric: Returns 'black'
        good_threshold: Minimum value for green (good/safe).
            Must be greater than warning_threshold.
        warning_threshold: Minimum value for yellow (warning).
            Values below this are red (critical/poor).
        
    Returns:
        Color string:
            - '#28a745' (green): For values >= good_threshold
            - '#ffc107' (yellow): For warning_threshold <= values < good_threshold
            - '#dc3545' (red): For values < warning_threshold
            - 'black': For non-numeric or invalid values
            
    Example:
        >>> # Score-based coloring (higher is better)
        >>> create_traffic_light_colors(95, good_threshold=80, warning_threshold=60)
        '#28a745'  # Green
        
        >>> create_traffic_light_colors(70, good_threshold=80, warning_threshold=60)
        '#ffc107'  # Yellow
        
        >>> create_traffic_light_colors(45, good_threshold=80, warning_threshold=60)
        '#dc3545'  # Red
        
        >>> # Risk-based coloring (lower is better)
        >>> # Use with negative thresholds or transform values
        >>> create_traffic_light_colors(10, good_threshold=25, warning_threshold=50)
        '#28a745'  # Green (below 25)
        
        >>> create_traffic_light_colors('N/A', good_threshold=80, warning_threshold=60)
        'black'
        
    Note:
        - Thresholds are inclusive at their lower bounds
        - Bootstrap color palette for consistency
        - For "lower is better" metrics, consider transforming values
          or using negative thresholds
    """
    try:
        val = float(value)
        if val >= good_threshold:
            return '#28a745'  # Green
        elif val >= warning_threshold:
            return '#ffc107'  # Yellow
        else:
            return '#dc3545'  # Red
    except (ValueError, TypeError):
        return 'black'

def create_growth_colors(
    df: pd.DataFrame, 
    column_order: List[str], 
    growth_columns: List[str]
) -> pd.DataFrame:
    """Apply growth-based coloring to specified columns.
    
    A convenience wrapper around create_dynamic_colors that applies the
    growth_color_function to specified columns. This provides a quick way
    to add green/red coloring for growth rates, changes, and deltas.
    
    Args:
        df: DataFrame containing the table data. Original is not modified.
        column_order: List of column names in the exact order they appear
            in the table. Must match the table's column configuration.
        growth_columns: List of column names containing growth/change values
            that should be colored. Non-existent columns are ignored.
        
    Returns:
        New DataFrame with original data plus color columns (_color_col_N)
        for use in Plotly table configurations.
        
    Example:
        >>> df = pd.DataFrame({
        ...     'product': ['A', 'B', 'C'],
        ...     'revenue': [100, 200, 150],
        ...     'growth_rate': [0.15, -0.05, 0.10],
        ...     'yoy_change': [10, -20, 15]
        ... })
        >>> 
        >>> df_colored = create_growth_colors(
        ...     df,
        ...     column_order=['product', 'revenue', 'growth_rate', 'yoy_change'],
        ...     growth_columns=['growth_rate', 'yoy_change']
        ... )
        >>> 
        >>> # Use in YAML:
        >>> # cells:
        >>> #   font:
        >>> #     color: [$_color_col_0, $_color_col_1, $_color_col_2, $_color_col_3]
        
    Note:
        - Positive values (including zero) are green
        - Negative values are red
        - Non-numeric values are black
        - See create_dynamic_colors for detailed behavior
    """
    return create_dynamic_colors(df, column_order, growth_color_function, growth_columns)

def create_performance_colors(
    df: pd.DataFrame, 
    column_order: List[str], 
    performance_columns: List[str], 
    threshold: float = 0.0
) -> pd.DataFrame:
    """Apply threshold-based coloring to performance metric columns.
    
    A convenience wrapper that applies performance_color_function with a
    specified threshold to selected columns. Useful for KPIs, targets,
    and any metrics with a clear performance cutoff.
    
    Args:
        df: DataFrame containing the table data. Original is not modified.
        column_order: List of column names in the exact order they appear
            in the table. Must match the table's column configuration.
        performance_columns: List of column names containing performance
            metrics that should be colored. Non-existent columns are ignored.
        threshold: The minimum value to be considered good performance.
            Values >= threshold are green, < threshold are red.
            Defaults to 0.0.
        
    Returns:
        New DataFrame with original data plus color columns (_color_col_N)
        for use in Plotly table configurations.
        
    Example:
        >>> df = pd.DataFrame({
        ...     'team': ['A', 'B', 'C'],
        ...     'efficiency': [0.92, 0.78, 0.85],
        ...     'target_met': [105, 95, 98],
        ...     'score': [88, 92, 79]
        ... })
        >>> 
        >>> # Color efficiency with 0.80 threshold
        >>> df_colored = create_performance_colors(
        ...     df,
        ...     column_order=['team', 'efficiency', 'target_met', 'score'],
        ...     performance_columns=['efficiency'],
        ...     threshold=0.80
        ... )
        >>> 
        >>> # Multiple columns with 100% target threshold  
        >>> df_colored = create_performance_colors(
        ...     df,
        ...     column_order=['team', 'efficiency', 'target_met', 'score'],
        ...     performance_columns=['target_met', 'score'],
        ...     threshold=100
        ... )
        
    Note:
        - Single threshold applies to all performance_columns
        - For different thresholds per column, call multiple times
        - Values exactly at threshold are colored green
        - See create_dynamic_colors for detailed behavior
    """
    def perf_func(value):
        return performance_color_function(value, threshold)
    
    return create_dynamic_colors(df, column_order, perf_func, performance_columns)
