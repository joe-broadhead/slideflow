"""
Table utility functions for slideflow

High-order functions for creating dynamic table formatting, coloring, and data processing.
"""

from typing import List, Callable, Any


def create_dynamic_colors(df, column_order: List[str], color_func: Callable, target_columns: List[str]):
    """
    High-order function to create dynamic color arrays for Plotly tables.
    
    This function applies a color function to specified columns and creates individual
    color columns that can be referenced in Plotly table configurations.
    
    Args:
        df: DataFrame with the table data
        column_order: List of column names in the order they appear in the table
        color_func: Function that takes a value and returns a color string
        target_columns: List of column names that should have the color function applied
        
    Returns:
        DataFrame with additional color columns (_color_col_0, _color_col_1, etc.)
        
    Example:
        # Growth coloring function
        def growth_colors(value):
            return '#28a745' if value >= 0 else '#dc3545'
            
        # Apply to growth columns
        df = create_dynamic_colors(
            df, 
            column_order=['name', 'value', 'change'],
            color_func=growth_colors,
            target_columns=['change']
        )
        
        # In YAML config:
        color: [$_color_col_0, $_color_col_1, $_color_col_2]
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
    """
    Built-in color function for growth values.
    Returns green for positive values, red for negative values.
    
    Args:
        value: Numeric value to evaluate
        
    Returns:
        Color string ('#28a745' for positive, '#dc3545' for negative)
    """
    try:
        return '#28a745' if float(value) >= 0 else '#dc3545'
    except (ValueError, TypeError):
        return 'black'


def performance_color_function(value: Any, threshold: float = 0.0) -> str:
    """
    Built-in color function for performance metrics with custom threshold.
    
    Args:
        value: Numeric value to evaluate
        threshold: Threshold value (default 0.0)
        
    Returns:
        Color string ('#28a745' for above threshold, '#dc3545' for below)
    """
    try:
        return '#28a745' if float(value) >= threshold else '#dc3545'
    except (ValueError, TypeError):
        return 'black'


def create_traffic_light_colors(value: Any, good_threshold: float, warning_threshold: float) -> str:
    """
    Built-in color function for traffic light coloring (green/yellow/red).
    
    Args:
        value: Numeric value to evaluate
        good_threshold: Minimum value for green
        warning_threshold: Minimum value for yellow (below this is red)
        
    Returns:
        Color string ('#28a745' green, '#ffc107' yellow, '#dc3545' red)
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


# Convenience functions for common use cases
def create_growth_colors(df, column_order: List[str], growth_columns: List[str]):
    """
    Convenience function for growth column coloring.
    
    Args:
        df: DataFrame with the table data
        column_order: List of column names in table order
        growth_columns: List of columns containing growth values
        
    Returns:
        DataFrame with color columns for growth values (green/red)
    """
    return create_dynamic_colors(df, column_order, growth_color_function, growth_columns)


def create_performance_colors(df, column_order: List[str], performance_columns: List[str], threshold: float = 0.0):
    """
    Convenience function for performance metric coloring.
    
    Args:
        df: DataFrame with the table data
        column_order: List of column names in table order
        performance_columns: List of columns containing performance metrics
        threshold: Performance threshold (default 0.0)
        
    Returns:
        DataFrame with color columns for performance values
    """
    def perf_func(value):
        return performance_color_function(value, threshold)
    
    return create_dynamic_colors(df, column_order, perf_func, performance_columns)