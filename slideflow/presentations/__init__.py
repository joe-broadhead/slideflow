"""Slideflow Presentations Module - Dynamic Presentation Generation System.

This module provides a comprehensive framework for creating, managing, and
rendering presentations across multiple platforms with dynamic data integration.
The system supports automated chart generation, text replacement, and flexible
positioning using a declarative configuration approach.

Architecture Overview:
    The presentations module follows a layered architecture:
    
    1. Configuration Layer (config.py):
       - Type-safe configuration models using Pydantic
       - Hierarchical structure from presentations down to individual elements
       - Support for YAML-based configuration with template resolution
    
    2. Builder Layer (builder.py):
       - Factory pattern for constructing presentations from configuration
       - Integration with ConfigLoader for template and function resolution
       - Automatic validation and type conversion
    
    3. Provider Layer (providers/):
       - Platform-specific implementations (Google Slides, PowerPoint, etc.)
       - Unified interface for presentation operations
       - Authentication and API management
    
    4. Content Layer (base.py, charts.py):
       - Core presentation and slide models
       - Chart generation with multiple visualization backends
       - Text replacement system with data source integration
    
    5. Utilities Layer (positioning.py):
       - Coordinate system conversion and positioning calculations
       - Safe expression evaluation for dynamic positioning
       - Alignment and dimension validation

Key Features:
    - Multi-platform presentation support (Google Slides, extensible to others)
    - Dynamic chart generation using Plotly, custom functions, or templates
    - Intelligent text replacement with AI and data-driven content
    - Flexible positioning with expressions and alignment systems
    - Concurrent data fetching and processing for performance
    - Type-safe configuration with comprehensive validation
    - Template-based reusable presentation definitions
    - Automatic image upload and management

Example Usage:
    Creating a presentation from YAML configuration:
    
    >>> from slideflow.presentations import PresentationBuilder
    >>> from pathlib import Path
    >>> 
    >>> # Build presentation from YAML
    >>> presentation = PresentationBuilder.from_yaml(
    ...     yaml_path=Path("monthly_report.yaml"),
    ...     params={"month": "March", "year": "2024"}
    ... )
    >>> 
    >>> # Render to Google Slides
    >>> result = presentation.render()
    >>> print(f"Presentation created: {result.presentation_url}")
    >>> print(f"Generated {result.charts_generated} charts")
    >>> print(f"Made {result.replacements_made} text replacements")
    
    Programmatic presentation creation:
    
    >>> from slideflow.presentations import (
    ...     Presentation, Slide, PlotlyGraphObjects,
    ...     GoogleSlidesProvider, GoogleSlidesProviderConfig
    ... )
    >>> 
    >>> # Create provider
    >>> provider_config = GoogleSlidesProviderConfig(
    ...     provider_type="google_slides",
    ...     credentials_path="/path/to/creds.json"
    ... )
    >>> provider = GoogleSlidesProvider(provider_config)
    >>> 
    >>> # Create chart
    >>> chart = PlotlyGraphObjects(
    ...     type="plotly_go",
    ...     title="Monthly Revenue",
    ...     traces=[{
    ...         "type": "scatter",
    ...         "x": "$month",
    ...         "y": "$revenue",
    ...         "mode": "lines+markers"
    ...     }],
    ...     data_source=csv_data_source,
    ...     x=100, y=150, width=500, height=400
    ... )
    >>> 
    >>> # Create slide
    >>> slide = Slide(
    ...     id="revenue_slide",
    ...     title="Revenue Analysis",
    ...     charts=[chart],
    ...     replacements=[text_replacement]
    ... )
    >>> 
    >>> # Create and render presentation
    >>> presentation = Presentation(
    ...     name="Q1 Financial Report",
    ...     slides=[slide],
    ...     provider=provider
    ... )
    >>> result = presentation.render()

Common Workflows:
    1. YAML-driven presentations for business reporting
    2. Programmatic chart generation from database queries
    3. Template-based presentation creation for consistent branding
    4. Multi-slide dashboards with real-time data integration
    5. Automated report generation for scheduled delivery

Integration Points:
    - Data Sources: CSV, JSON, Databricks, DBT, custom connectors
    - Chart Libraries: Plotly (built-in), matplotlib (via custom functions)
    - AI Services: OpenAI, Anthropic, custom providers for text generation
    - Cloud Platforms: Google Workspace, extensible to Microsoft 365
    - Template Engines: Jinja2 for configuration and chart templates

Performance Features:
    - Concurrent data fetching to minimize latency
    - Intelligent caching to avoid redundant API calls
    - Batch operations for efficient platform API usage
    - Expression-based positioning for responsive layouts
    - Parallel chart generation for multi-chart presentations
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