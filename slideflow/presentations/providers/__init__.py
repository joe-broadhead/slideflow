"""Presentation providers for various platforms in Slideflow.

This module provides a unified interface for creating and managing presentations
across different platforms. The provider system follows a plugin architecture
where each platform has its own specialized provider implementation.

The provider system includes:
    - Base classes and interfaces for all providers
    - Platform-specific provider implementations
    - Factory functions for provider instantiation
    - Consistent APIs for presentation operations

Architecture:
    All providers inherit from PresentationProvider base class and implement a
    consistent interface for presentation creation, modification, and management.
    Each provider handles platform-specific authentication, API calls, and
    presentation formatting.

Key Features:
    - Consistent interface across all presentation platforms
    - Type-safe provider instantiation with factory pattern
    - Authentication management for each platform
    - Error handling and retry mechanisms
    - Extensible design for adding new platforms

Example:
    Using providers to create presentations:
    
    >>> from slideflow.presentations.providers import ProviderFactory
    >>> from slideflow.presentations.providers import GoogleSlidesProviderConfig
    >>> 
    >>> # Create a Google Slides provider configuration
    >>> config = GoogleSlidesProviderConfig(
    ...     credentials="/path/to/credentials.json"
    ... )
    >>> 
    >>> # Create provider using factory
    >>> provider = ProviderFactory.create_provider(config)
    >>> 
    >>> # Create a new presentation
    >>> presentation_id = provider.create_presentation("Monthly Report")
    >>> print(f"Created presentation: {presentation_id}")

Available Providers:
    - GoogleSlidesProvider: For Google Slides presentation creation and management

Available Configurations:
    - GoogleSlidesProviderConfig: Configuration for Google Slides provider

Result Classes:
    - ProviderPresentationResult: Result from presentation operations
    - ProviderSlideResult: Result from individual slide operations

Factory:
    - ProviderFactory: Factory class for provider instantiation and registration
"""

from slideflow.presentations.providers.base import (
    PresentationProvider,
    PresentationProviderConfig,
    ProviderPresentationResult,
    ProviderSlideResult
)
from slideflow.presentations.providers.factory import ProviderFactory
from slideflow.presentations.providers.google_slides import GoogleSlidesProvider, GoogleSlidesProviderConfig

__all__ = [
    "PresentationProvider",
    "PresentationProviderConfig", 
    "ProviderPresentationResult",
    "ProviderSlideResult",
    "GoogleSlidesProvider",
    "GoogleSlidesProviderConfig",
    "ProviderFactory"
]
