from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Annotated

class ReplacementSpec(BaseModel):
    """Replacement specification with embedded data source."""
    
    model_config = ConfigDict(extra = "forbid")
    
    type: Annotated[str, Field(..., description = "Replacement type: text, ai_text, or table")]
    config: Annotated[Dict[str, Any], Field(..., description = "Replacement configuration including data_source")]

class ChartSpec(BaseModel):
    """Chart specification with embedded data source."""
    
    model_config = ConfigDict(extra = "forbid")
    
    type: Annotated[str, Field(..., description = "Chart type: plotly_go or custom")]
    config: Annotated[Dict[str, Any], Field(..., description = "Chart configuration including data_source")]

class SlideSpec(BaseModel):
    """Specification for a single slide."""
    
    model_config = ConfigDict(extra = "forbid")
    
    id: Annotated[str, Field(..., description = "Slide ID in the Google Slides template")]
    title: Annotated[Optional[str], Field(None, description = "Slide title for documentation")]
    replacements: Annotated[List[ReplacementSpec], Field(default_factory = list, description = "Text replacements for this slide")]
    charts: Annotated[List[ChartSpec], Field(default_factory = list, description = "Charts to generate for this slide")]

class PresentationSpec(BaseModel):
    """Specification for the entire presentation."""
    
    model_config = ConfigDict(extra = "forbid")
    
    name: Annotated[str, Field(..., description = "Presentation name")]
    slides: Annotated[List[SlideSpec], Field(..., description = "List of slides in the presentation")]

class ProviderConfig(BaseModel):
    """Configuration for presentation provider (Google Slides, PowerPoint, etc.)."""
    
    model_config = ConfigDict(extra = "forbid")
    
    type: Annotated[str, Field(..., description = "Provider type: 'google_slides', 'powerpoint', etc.")]
    config: Annotated[Dict[str, Any], Field(..., description = "Provider-specific configuration")]


class PresentationConfig(BaseModel):
    """Top-level configuration for building presentations."""
    
    model_config = ConfigDict(extra = "forbid")
    
    presentation: Annotated[PresentationSpec, Field(..., description = "Presentation specification")]
    provider: Annotated[ProviderConfig, Field(..., description = "Presentation provider configuration")]
    template_paths: Annotated[Optional[List[str]], Field(None, description = "Custom template search paths (in priority order)")]
