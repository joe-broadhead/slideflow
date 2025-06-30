"""Slideflow Presentations Module

This module provides functionality for creating and managing
Google Slides presentations with dynamic data integration.
"""

from slideflow.presentations.config import (
    PresentationConfig,
    PresentationSpec,
    SlideSpec,
    ProviderConfig,
    ReplacementSpec,
    ChartSpec,
)
from slideflow.presentations.builder import PresentationBuilder
from slideflow.presentations.providers.google_slides import GoogleSlidesProvider
from slideflow.presentations.base import Presentation, Slide, PresentationResult, SlideResult
from slideflow.presentations.charts import BaseChart, PlotlyGraphObjects, CustomChart, TemplateChart, ChartUnion
from slideflow.presentations.positioning import compute_chart_dimensions, safe_eval_expression, convert_dimensions, apply_alignment

__all__ = [
    # Base classes
    "Presentation",
    "Slide",
    "PresentationResult",
    "SlideResult",
    # Configuration
    "PresentationConfig",
    "PresentationSpec",
    "SlideSpec",
    "ProviderConfig",
    "ReplacementSpec",
    "ChartSpec",
    # Charts
    "BaseChart",
    "PlotlyGraphObjects",
    "CustomChart",
    "TemplateChart",
    "ChartUnion",
    # Builder and services
    "PresentationBuilder",
    "GoogleSlidesProvider",
    # Positioning utilities
    "compute_chart_dimensions",
    "safe_eval_expression", 
    "convert_dimensions",
    "apply_alignment",
]

# Rebuild models after all imports
Slide.model_rebuild()
Presentation.model_rebuild()