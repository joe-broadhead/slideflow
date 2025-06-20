"""
SlideFlow - Automated Google Slides presentation builder
"""

__version__ = "0.0.0"

# Core presentation components
from .presentation import Presentation, Slide, User

# Data management
from .data import DataManager, get_data_connector, DataSourceConfig

# Chart generation
from .chart import Chart, BUILT_IN_CHARTS

# Replacements
from .replacements import TextReplacement, TableReplacement, AITextReplacement

# AI providers
from .ai import OpenAIProvider, GeminiProvider, AI_PROVIDERS

# Utilities
from .utils import load_function_registry, get_credentials

__all__ = [
    # Core classes
    'Presentation',
    'Slide', 
    'User',
    
    # Data management
    'DataManager',
    'get_data_connector',
    'DataSourceConfig',
    
    # Chart generation
    'Chart',
    'BUILT_IN_CHARTS',
    
    # Replacements
    'TextReplacement',
    'TableReplacement', 
    'AITextReplacement',
    
    # AI providers
    'OpenAIProvider',
    'GeminiProvider',
    'AI_PROVIDERS',
    
    # Utilities
    'load_function_registry',
    'get_credentials',
]