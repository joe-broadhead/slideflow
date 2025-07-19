"""AI module for Slideflow.

This module provides AI-powered text generation capabilities for presentations.
It includes a provider system that supports multiple AI backends (OpenAI, Gemini)
and a registry system for managing and extending AI providers.

The module provides:
    - Base AI provider interface for implementing new providers
    - Built-in providers for OpenAI and Google Gemini
    - Registry system for discovering and managing providers
    - Factory functions for creating provider instances

Example:
    Basic usage with OpenAI provider::

        from slideflow.ai import OpenAIProvider, create_provider
        
        # Direct instantiation
        provider = OpenAIProvider(api_key="your-api-key")
        result = provider.generate("Summarize Q3 performance")
        
        # Using factory with registry
        provider = create_provider("openai", api_key="your-api-key")
        result = provider.generate("Create executive summary")

Attributes:
    ai_provider_registry: Global registry instance for AI providers
"""

from slideflow.ai.providers import (
    AIProvider, OpenAIProvider, GeminiProvider
)
from slideflow.ai.registry import (
    ai_provider_registry, get_provider_class, register_provider, 
    list_available_providers, create_provider
)

__all__ = [
    'AIProvider', 
    'OpenAIProvider', 
    'GeminiProvider',
    'ai_provider_registry',
    'get_provider_class',
    'register_provider',
    'list_available_providers',
    'create_provider'
]
