from typing import Optional, List, Dict, Any
import pandas as pd
from pydantic import BaseModel, Field, ConfigDict
from slideflow.utilities.data_transforms import apply_data_transforms

class BaseReplacement(BaseModel):
    """
    Base class for all content replacements in a slide.
    Uses a `type` field as the discriminator.
    """
    type: str = Field(..., description = "Discriminator for replacement type")
    data_transforms: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        description="Optional data transformations to apply (resolved by ConfigLoader)"
    )

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
        arbitrary_types_allowed = True
    )

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch data for this replacement.
        Should be overridden by subclasses that need data fetching.
        Returns None by default.
        """
        return None
    
    def apply_data_transforms(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply data transformations using the shared function."""
        return apply_data_transforms(self.data_transforms, df)
