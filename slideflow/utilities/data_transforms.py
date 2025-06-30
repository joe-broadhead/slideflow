import pandas as pd
from typing import Optional, List, Dict, Any

from slideflow.utilities.exceptions import DataTransformError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

def apply_data_transforms(data_transforms: Optional[List[Dict[str, Any]]], df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply data transformations to the DataFrame.
    
    This is a standalone function that can be used by any class
    that needs to apply data transformations.
    
    Args:
        data_transforms: List of transformation configurations
        df: Original DataFrame from data source
        
    Returns:
        Transformed DataFrame
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
