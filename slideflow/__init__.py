__version__ = "0.0.0"

# Core data functionality
from slideflow.data import (
    DataSourceCache, get_data_cache, DataSourceConfig,
    DataConnector, BaseSourceConfig,
    CSVConnector, CSVSourceConfig,
    JSONConnector, JSONSourceConfig,
    DatabricksConnector, DatabricksSourceConfig,
    DBTDatabricksConnector, DBTDatabricksSourceConfig
)

# Replacement functionality  
from slideflow.replacements import (
    BaseReplacement, TextReplacement, 
    TableReplacement, AITextReplacement,
    ReplacementUnion, dataframe_to_replacement_object
)

# AI providers
from slideflow.ai import (
    AIProvider, OpenAIProvider, GeminiProvider
)

# Presentation functionality
from slideflow.presentations import (
    PresentationBuilder, BaseChart, PlotlyGraphObjects, 
    CustomChart, TemplateChart, ChartUnion
)

# Utilities
from slideflow.utilities import ConfigLoader
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.builtins.formatting import (
    green_or_red, abbreviate, 
    format_currency, percentage
)

# Core registry utilities for extensibility
from slideflow.core.registry import (
    BaseRegistry, FunctionRegistry, ClassRegistry, ProviderRegistry,
    create_function_registry, create_class_registry, create_provider_registry
)

# CLI
from slideflow.cli import app as cli_app

# Exceptions
from slideflow.utilities.exceptions import (
    SlideFlowError, ConfigurationError, DataSourceError, DataTransformError,
    ProviderError, RenderingError, AuthenticationError, ChartGenerationError,
    ReplacementError
)

__all__ = [
    # Version
    '__version__',
    
    # Data
    'DataSourceCache', 'get_data_cache', 'DataSourceConfig',
    'DataConnector', 'BaseSourceConfig',
    'CSVConnector', 'CSVSourceConfig',
    'JSONConnector', 'JSONSourceConfig', 
    'DatabricksConnector', 'DatabricksSourceConfig',
    'DBTDatabricksConnector', 'DBTDatabricksSourceConfig',
    
    # Replacements
    'BaseReplacement', 'TextReplacement',
    'TableReplacement', 'AITextReplacement',
    'ReplacementUnion', 'dataframe_to_replacement_object',
    
    # AI
    'AIProvider', 'OpenAIProvider', 'GeminiProvider',
    
    # Presentations
    'PresentationBuilder', 'BaseChart', 'PlotlyGraphObjects',
    'CustomChart', 'TemplateChart', 'ChartUnion',
    
    # Utilities
    'ConfigLoader', 'apply_data_transforms',
    'green_or_red', 'abbreviate', 'format_currency', 'percentage',
    
    # Core registry utilities
    'BaseRegistry', 'FunctionRegistry', 'ClassRegistry', 'ProviderRegistry',
    'create_function_registry', 'create_class_registry', 'create_provider_registry',
    
    # CLI
    'cli_app',
    
    # Exceptions
    'SlideFlowError', 'ConfigurationError', 'DataSourceError', 'DataTransformError',
    'ProviderError', 'RenderingError', 'AuthenticationError', 'ChartGenerationError',
    'ReplacementError',
]