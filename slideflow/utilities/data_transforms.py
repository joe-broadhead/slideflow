"""Data transformation pipeline for preprocessing DataFrames in Slideflow.

This module provides the core data transformation functionality used throughout
Slideflow for preprocessing data before it's used in charts, replacements, and
other content generation. The transformation system is designed to be flexible,
reusable, and easily configurable.

Key Features:
    - Function-based transformation pipeline
    - Comprehensive error handling with context preservation
    - Integration with logging system for debugging
    - Support for custom transformation functions
    - Safe handling of empty or None DataFrames
    - Detailed error reporting with DataFrame state information

Example:
    Basic data transformation usage:
    
    >>> import pandas as pd
    >>> from slideflow.utilities.data_transforms import apply_data_transforms
    >>> 
    >>> # Sample DataFrame
    >>> df = pd.DataFrame({
    ...     'sales': [100, 200, 300, 400],
    ...     'region': ['North', 'South', 'East', 'West']
    ... })
    >>> 
    >>> # Define transformations
    >>> def filter_high_sales(df, threshold=250):
    ...     return df[df['sales'] > threshold]
    >>> 
    >>> def add_growth_column(df, base_value=100):
    ...     df['growth'] = ((df['sales'] - base_value) / base_value) * 100
    ...     return df
    >>> 
    >>> transforms = [
    ...     {
    ...         'transform_fn': filter_high_sales,
    ...         'transform_args': {'threshold': 200}
    ...     },
    ...     {
    ...         'transform_fn': add_growth_column,
    ...         'transform_args': {'base_value': 150}
    ...     }
    ... ]
    >>> 
    >>> # Apply transformations
    >>> result_df = apply_data_transforms(transforms, df)
    >>> # Result: DataFrame with sales > 200 and growth column added

Transformation Function Structure:
    Each transformation is a dictionary containing:
    - 'transform_fn': Callable that takes DataFrame as first argument
    - 'transform_args': Optional dict of keyword arguments for the function
    
    Functions should return a modified DataFrame and handle their own
    validation and error cases.

Error Handling:
    The system provides detailed error context including:
    - Function name and arguments
    - DataFrame shape and columns before transformation
    - Original exception details
    - Transformation position in the pipeline
"""

import pandas as pd
from typing import Optional, List, Dict, Any

from slideflow.utilities.logging import get_logger
from slideflow.utilities.exceptions import DataTransformError

logger = get_logger(__name__)

def apply_data_transforms(data_transforms: Optional[List[Dict[str, Any]]], df: pd.DataFrame) -> pd.DataFrame:
    """Apply a sequence of data transformations to a DataFrame.
    
    This function executes a pipeline of transformation functions on a DataFrame,
    applying them in sequence and handling errors with detailed context. It's
    designed to be used throughout Slideflow wherever data preprocessing is needed.
    
    The transformation pipeline is flexible and supports any function that:
    1. Takes a DataFrame as the first argument
    2. Returns a modified DataFrame
    3. Accepts keyword arguments for configuration
    
    Safety Features:
    - Handles None or empty transformation lists gracefully
    - Safely processes empty DataFrames
    - Preserves original DataFrame (works on copies)
    - Provides detailed error context for debugging
    - Logs transformation progress for monitoring
    
    Args:
        data_transforms: List of transformation configuration dictionaries.
            Each dict should contain:
            - 'transform_fn': Callable function that processes DataFrames
            - 'transform_args': Optional dict of keyword arguments
            Pass None or empty list to return DataFrame unchanged.
        df: Input DataFrame to transform. Can be None or empty, which will
            be returned as-is.
            
    Returns:
        Transformed DataFrame with all transformations applied in sequence.
        Returns original DataFrame if no transformations are specified or
        if input DataFrame is None/empty.
        
    Raises:
        DataTransformError: If any transformation function fails. The error
            includes detailed context about the failure including function name,
            arguments, DataFrame state, and original exception.
            
    Example:
        Filtering and aggregation pipeline:
        
        >>> import pandas as pd
        >>> 
        >>> df = pd.DataFrame({
        ...     'product': ['A', 'B', 'A', 'B', 'C'],
        ...     'sales': [100, 200, 150, 250, 300],
        ...     'region': ['US', 'EU', 'US', 'EU', 'AS']
        ... })
        >>> 
        >>> def filter_by_region(df, regions):
        ...     return df[df['region'].isin(regions)]
        >>> 
        >>> def aggregate_by_product(df):
        ...     return df.groupby('product')['sales'].sum().reset_index()
        >>> 
        >>> transforms = [
        ...     {
        ...         'transform_fn': filter_by_region,
        ...         'transform_args': {'regions': ['US', 'EU']}
        ...     },
        ...     {
        ...         'transform_fn': aggregate_by_product
        ...     }
        ... ]
        >>> 
        >>> result = apply_data_transforms(transforms, df)
        >>> # Result: DataFrame with products A, B aggregated by sales
        
        Error handling example:
        
        >>> def failing_transform(df, invalid_column):
        ...     return df[invalid_column]  # Will raise KeyError
        >>> 
        >>> transforms = [{
        ...     'transform_fn': failing_transform,
        ...     'transform_args': {'invalid_column': 'nonexistent'}
        ... }]
        >>> 
        >>> try:
        ...     result = apply_data_transforms(transforms, df)
        ... except DataTransformError as e:
        ...     print(f"Transform failed: {e}")
        ...     # Error includes function name, args, DataFrame info
        
        No-op scenarios:
        
        >>> # No transformations
        >>> result = apply_data_transforms(None, df)
        >>> assert result is df  # Same object returned
        >>> 
        >>> # Empty transformation list
        >>> result = apply_data_transforms([], df)
        >>> assert result is df  # Same object returned
        >>> 
        >>> # Empty DataFrame
        >>> empty_df = pd.DataFrame()
        >>> result = apply_data_transforms(transforms, empty_df)
        >>> assert result is empty_df  # Same object returned
    """
    if not data_transforms or df is None or (df is not None and df.empty):
        return df
        
    transformed_df = df.copy()
    
    for i, transform in enumerate(data_transforms):
        if 'transform_fn' in transform and callable(transform['transform_fn']):
            func = transform['transform_fn']
            args = transform.get('transform_args', {})
            
            try:
                transformed_df = func(transformed_df, **args)
                logger.debug(f"Applied transform {i+1}/{len(data_transforms)}: {func.__name__}")
            except Exception as e:
                transform_name = getattr(func, '__name__', str(func))
                logger.error(f"Transform function '{transform_name}' failed: {e}")
                logger.error(f"Transform args: {args}")
                logger.error(f"DataFrame shape before transform: {transformed_df.shape}")
                logger.error(f"DataFrame columns: {list(transformed_df.columns)}")
                raise DataTransformError(
                    f"Transform function '{transform_name}' failed: {e}. "
                    f"Args: {args}. DataFrame shape: {transformed_df.shape}. "
                    f"Available columns: {list(transformed_df.columns)}"
                ) from e
        
    return transformed_df
