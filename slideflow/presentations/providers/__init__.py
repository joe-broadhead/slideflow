"""
Presentation Provider Interfaces

This module defines abstract interfaces for presentation providers,
enabling support for multiple presentation platforms (Google Slides, PowerPoint, PDF, etc.)
"""

from slideflow.presentations.providers.base import (
    PresentationProvider,
    PresentationProviderConfig,
    ProviderPresentationResult,
    ProviderSlideResult
)
from slideflow.presentations.providers.google_slides import GoogleSlidesProvider, GoogleSlidesProviderConfig
from slideflow.presentations.providers.factory import ProviderFactory

__all__ = [
    "PresentationProvider",
    "PresentationProviderConfig", 
    "ProviderPresentationResult",
    "ProviderSlideResult",
    "GoogleSlidesProvider",
    "GoogleSlidesProviderConfig",
    "ProviderFactory"
]