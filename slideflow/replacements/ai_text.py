"""AI-powered text replacement for intelligent content generation.

This module provides the AITextReplacement class for generating dynamic text
content using artificial intelligence providers. It supports multiple AI
services and can integrate data sources to create context-aware, intelligent
replacements for presentation content.

The AI text replacement system supports:
    - Multiple AI providers (OpenAI, Anthropic, custom providers)
    - Data-driven prompts with context injection
    - Flexible provider configuration and instantiation
    - Custom callable functions for specialized AI logic
    - Automatic prompt enhancement with data context

Key Features:
    - Provider abstraction supporting multiple AI services
    - Automatic data context injection into prompts
    - Flexible provider instantiation (string, class, instance, callable)
    - Data transformation pipeline integration
    - Error handling for provider failures

Example:
    Basic AI text generation:
    
    >>> from slideflow.replacements.ai_text import AITextReplacement
    >>> 
    >>> replacement = AITextReplacement(
    ...     type="ai_text",
    ...     placeholder="{{EXECUTIVE_SUMMARY}}",
    ...     prompt="Generate a 3-sentence executive summary of the key findings",
    ...     provider="openai",
    ...     provider_args={"model": "gpt-4", "max_tokens": 150}
    ... )
    >>> summary = replacement.get_replacement()
    
    AI generation with data context:
    
    >>> replacement = AITextReplacement(
    ...     type="ai_text",
    ...     placeholder="{{INSIGHTS}}",
    ...     prompt="Analyze this sales data and provide 3 key insights",
    ...     provider="anthropic",
    ...     data_source=sales_data_source,
    ...     provider_args={"model": "claude-3-sonnet"}
    ... )
    >>> insights = replacement.get_replacement()
    
    Custom AI function:
    
    >>> def custom_analyzer(prompt, data_context=None, temperature=0.7):
    ...     # Custom AI logic here
    ...     return "Custom AI response based on prompt and data"
    >>> 
    >>> replacement = AITextReplacement(
    ...     type="ai_text",
    ...     placeholder="{{ANALYSIS}}",
    ...     prompt="Provide detailed analysis",
    ...     provider=custom_analyzer,
    ...     provider_args={"temperature": 0.5}
    ... )
"""

import inspect
import pandas as pd
from pydantic import Field, ConfigDict
from typing import (
    Any,
    Type,
    Dict,
    Union,
    Literal,
    Callable,
    Annotated,
    Optional
)

from slideflow.ai.providers import AIProvider
from slideflow.ai.registry import get_provider_class
from slideflow.replacements.base import BaseReplacement
from slideflow.utilities.exceptions import ReplacementError
from slideflow.data.connectors.connect import DataSourceConfig

class AITextReplacement(BaseReplacement):
    """AI-powered text replacement for intelligent content generation.
    
    This class generates dynamic text content using artificial intelligence
    providers. It can integrate with various AI services (OpenAI, Anthropic,
    custom providers) and automatically enhances prompts with data context
    when a data source is configured.
    
    The AI replacement system is designed to be flexible and extensible,
    supporting multiple provider types and configuration patterns:
    
    1. String provider names (resolved via registry)
    2. Provider classes (instantiated automatically)
    3. Provider instances (used directly)
    4. Custom callable functions (called with prompt and args)
    
    Provider Arguments:
        The provider_args dictionary is intelligently split between:
        - Initialization arguments (for provider construction)
        - Call arguments (for text generation method)
        
        This allows fine-grained control over both provider setup and
        generation parameters.
    
    Data Integration:
        When a data_source is configured, the fetched data is automatically
        formatted and appended to the prompt, providing context for the AI
        to generate more relevant and accurate content.
    
    Attributes:
        type: Always "ai_text" for this replacement type.
        placeholder: Template placeholder to replace with AI-generated content.
        prompt: Base prompt template for the AI provider.
        provider: AI provider specification (string, class, instance, or callable).
        provider_args: Configuration arguments for provider initialization and calls.
        data_source: Optional data source for context enhancement.
        
    Example:
        OpenAI text generation:
        
        >>> replacement = AITextReplacement(
        ...     type="ai_text",
        ...     placeholder="{{SUMMARY}}",
        ...     prompt="Summarize the key trends in this data",
        ...     provider="openai",
        ...     provider_args={
        ...         "api_key": "sk-...",  # Init arg
        ...         "model": "gpt-4",     # Call arg
        ...         "temperature": 0.7    # Call arg
        ...     },
        ...     data_source=trends_data
        ... )
        >>> result = replacement.get_replacement()
        
        Custom provider instance:
        
        >>> from slideflow.ai.providers import AnthropicProvider
        >>> provider_instance = AnthropicProvider(api_key="ak-...")
        >>> 
        >>> replacement = AITextReplacement(
        ...     type="ai_text",
        ...     placeholder="{{INSIGHTS}}",
        ...     prompt="Generate insights from this dataset",
        ...     provider=provider_instance,
        ...     provider_args={"model": "claude-3-sonnet"}
        ... )
        
        Custom callable function:
        
        >>> def specialized_ai_function(prompt, context_data=None, style="formal"):
        ...     # Custom AI logic with specialized processing
        ...     if context_data:
        ...         prompt += f"\n\nContext: {context_data}"
        ...     return generate_with_custom_logic(prompt, style=style)
        >>> 
        >>> replacement = AITextReplacement(
        ...     type="ai_text",
        ...     placeholder="{{ANALYSIS}}",
        ...     prompt="Analyze the following business metrics",
        ...     provider=specialized_ai_function,
        ...     provider_args={"style": "executive"}
        ... )
    """
    type: Annotated[Literal["ai_text"], Field("ai_text", description = "Discriminator for AI-text replacements")]
    placeholder: Annotated[str, Field(..., description = "Placeholder to replace (e.g. '{{SUMMARY}}')")]
    prompt: Annotated[str, Field(..., description = "Prompt template for the AI provider")]
    provider: Annotated[Union[str, Type[AIProvider], AIProvider, Callable[..., str]], Field(default = "openai", description = "Provider name, class, instance, or plain callable")]
    provider_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Keyword args for provider init & call")]
    data_source: Annotated[Optional[DataSourceConfig], Field(default = None, description = "Optional data source to include")]

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
        arbitrary_types_allowed = True
    )

    def _prepare_provider(self) -> tuple[Callable[..., str], dict[str, Any]]:
        """Prepare the AI provider for text generation.
        
        This method handles the complex logic of provider instantiation and
        configuration. It supports multiple provider types and intelligently
        splits provider arguments between initialization and call parameters.
        
        Provider Type Handling:
        1. String names: Resolved via the AI provider registry
        2. Provider classes: Instantiated with appropriate init args
        3. Provider instances: Used directly with call args
        4. Callable functions: Used as-is with all args as call args
        
        Argument Splitting:
        For provider classes, the method inspects the __init__ signature to
        determine which arguments are for initialization vs. text generation.
        This allows seamless configuration of both provider setup and
        generation parameters in a single provider_args dictionary.
        
        Returns:
            Tuple containing:
            - Callable function for text generation
            - Dictionary of arguments to pass to the generation call
            
        Raises:
            ReplacementError: If the provider type is invalid or unsupported.
            
        Example:
            Provider class with argument splitting:
            
            >>> # provider_args = {"api_key": "sk-...", "model": "gpt-4", "temperature": 0.7}
            >>> # __init__ signature: __init__(self, api_key)
            >>> # Result: init_args = {"api_key": "sk-..."}, call_args = {"model": "gpt-4", "temperature": 0.7}
            >>> fn, call_args = replacement._prepare_provider()
            >>> # fn is bound method of instantiated provider
            >>> # call_args contains generation parameters
        """
        Prov = self.provider
        args = dict(self.provider_args)

        # Handle string provider names using registry
        if isinstance(Prov, str):
            Prov = get_provider_class(Prov)

        if inspect.isclass(Prov) and issubclass(Prov, AIProvider):
            sig = inspect.signature(Prov.__init__)
            init_params = {p for p in sig.parameters if p != "self"}
            init_args = {k: v for k, v in args.items() if k in init_params}
            call_args = {k: v for k, v in args.items() if k not in init_params}
            instance = Prov(**init_args)
            return instance.generate_text, call_args

        if isinstance(Prov, AIProvider):
            return Prov.generate_text, args

        if callable(Prov):
            return Prov, args

        raise ReplacementError(f"Invalid AI provider: {Prov!r}")

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """Fetch data from the configured data source for prompt enhancement.
        
        When a data_source is configured, this method retrieves the data that
        will be used to enhance the AI prompt with relevant context. The data
        is typically converted to a structured format and appended to the prompt
        to provide the AI with specific information for generating targeted content.
        
        Returns:
            DataFrame containing the fetched data if a data source is configured,
            None if no data source is set (prompt will be used as-is).
            
        Example:
            >>> replacement = AITextReplacement(
            ...     type="ai_text",
            ...     placeholder="{{ANALYSIS}}",
            ...     prompt="Analyze this sales data",
            ...     data_source=sales_source
            ... )
            >>> data = replacement.fetch_data()
            >>> # Returns DataFrame with sales data for prompt context
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None

    def get_replacement(self) -> str:
        """Generate AI-powered text content for the replacement.
        
        This method orchestrates the complete AI text generation process:
        
        1. Start with the base prompt template
        2. Fetch data from data_source if configured
        3. Apply data transformations to the fetched data
        4. Enhance prompt with data context (formatted as records)
        5. Prepare the AI provider with proper configuration
        6. Generate text using the enhanced prompt
        7. Return the generated content as a string
        
        Data Context Enhancement:
            When data is available, it's converted to a list of dictionaries
            (records format) and appended to the prompt with a "Data:" prefix.
            This provides structured context that AI models can easily parse
            and incorporate into their responses.
        
        Returns:
            AI-generated text content ready for placeholder replacement.
            
        Raises:
            ReplacementError: If provider preparation fails.
            Any exception from the AI provider during text generation.
            
        Example:
            Basic AI generation:
            
            >>> replacement = AITextReplacement(
            ...     type="ai_text",
            ...     placeholder="{{SUMMARY}}",
            ...     prompt="Summarize key findings",
            ...     provider="openai"
            ... )
            >>> result = replacement.get_replacement()
            >>> # Returns: AI-generated summary text
            
            With data context:
            
            >>> replacement = AITextReplacement(
            ...     type="ai_text",
            ...     placeholder="{{INSIGHTS}}",
            ...     prompt="Generate insights from this data",
            ...     provider="anthropic",
            ...     data_source=metrics_source
            ... )
            >>> result = replacement.get_replacement()
            >>> # Prompt becomes: "Generate insights from this data\n\nData:\n[{metric records}]"
            >>> # Returns: AI-generated insights based on actual data
        """
        prompt = self.prompt

        df = self.fetch_data()
        if df is not None:
            df = self.apply_data_transforms(df)
            data = df.to_dict(orient = "records")
            prompt += f"\n\nData:\n{data}"

        fn, call_args = self._prepare_provider()
        return fn(prompt, **call_args)
