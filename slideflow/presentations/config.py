"""Configuration models for presentation generation in Slideflow.

This module defines the configuration schema for building presentations using
the Slideflow system. It provides Pydantic models that validate and structure
configuration data from YAML files or programmatic sources.

The configuration system follows a hierarchical structure:
    - PresentationConfig: Root configuration container
    - PresentationSpec: Defines presentation content and slides
    - SlideSpec: Individual slide configuration with content
    - ReplacementSpec: Text replacement configuration
    - ChartSpec: Chart generation configuration
    - ProviderConfig: Platform-specific provider settings

Key Features:
    - Type-safe configuration with Pydantic validation
    - Hierarchical structure that mirrors presentation organization
    - Flexible provider configuration for multiple platforms
    - Support for custom template paths
    - Embedded data source configurations

Example:
    Creating a presentation configuration:
    
    >>> from slideflow.presentations.config import PresentationConfig
    >>> 
    >>> config = PresentationConfig(
    ...     presentation=PresentationSpec(
    ...         name="Monthly Report",
    ...         slides=[
    ...             SlideSpec(
    ...                 id="slide_1",
    ...                 title="Overview",
    ...                 replacements=[
    ...                     ReplacementSpec(
    ...                         type="text",
    ...                         config={"placeholder": "{{MONTH}}", "value": "March"}
    ...                     )
    ...                 ],
    ...                 charts=[
    ...                     ChartSpec(
    ...                         type="plotly_go",
    ...                         config={"traces": [...], "data_source": {...}}
    ...                     )
    ...                 ]
    ...             )
    ...         ]
    ...     ),
    ...     provider=ProviderConfig(
    ...         type="google_slides",
    ...         config={"credentials_path": "/path/to/creds.json"}
    ...     )
    ... )

Validation:
    All configuration models include strict validation to ensure:
    - Required fields are present
    - Field types match expected schemas
    - No extra fields are allowed (extra="forbid")
    - Cross-field validation where applicable
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Annotated

class ReplacementSpec(BaseModel):
    """Configuration specification for text replacements in presentations.
    
    This model defines how text placeholders in presentation templates should
    be replaced with dynamic content. It supports various replacement types
    including static text, AI-generated content, and data-driven table
    replacements.
    
    The configuration is designed to work with the ConfigLoader system, which
    can resolve functions and template expressions before validation. The
    embedded data source configuration allows replacements to fetch data
    from external systems.
    
    Attributes:
        type: The replacement type identifier (text, ai_text, table) that
            determines which replacement class will be instantiated.
        config: Type-specific configuration dictionary containing all parameters
            needed by the replacement implementation, including optional
            data_source configuration.
            
    Example:
        Text replacement configuration:
        
        >>> text_replacement = ReplacementSpec(
        ...     type="text",
        ...     config={
        ...         "placeholder": "{{COMPANY_NAME}}",
        ...         "value": "Acme Corporation"
        ...     }
        ... )
        
        AI text replacement with data source:
        
        >>> ai_replacement = ReplacementSpec(
        ...     type="ai_text",
        ...     config={
        ...         "placeholder": "{{SUMMARY}}",
        ...         "prompt": "Summarize the key findings from this data",
        ...         "data_source": {
        ...             "type": "csv",
        ...             "name": "results",
        ...             "file_path": "analysis_results.csv"
        ...         }
        ...     }
        ... )
        
        Table replacement configuration:
        
        >>> table_replacement = ReplacementSpec(
        ...     type="table",
        ...     config={
        ...         "prefix": "METRIC_",
        ...         "data_source": {
        ...             "type": "databricks",
        ...             "name": "metrics",
        ...             "query": "SELECT metric_name, value FROM monthly_metrics"
        ...         }
        ...     }
        ... )
    """
    
    model_config = ConfigDict(extra = "forbid")
    
    type: Annotated[str, Field(..., description = "Replacement type: text, ai_text, or table")]
    config: Annotated[Dict[str, Any], Field(..., description = "Replacement configuration including data_source")]

class ChartSpec(BaseModel):
    """Configuration specification for charts in presentations.
    
    This model defines how charts should be generated and positioned within
    presentation slides. It supports multiple chart types including Plotly-based
    visualizations, custom chart functions, and template-driven charts.
    
    The configuration includes all parameters needed for chart generation
    including data sources, positioning, styling, and type-specific options.
    Charts can fetch data from external sources or use static data defined
    in the configuration.
    
    Attributes:
        type: The chart type identifier (plotly_go, custom, template) that
            determines which chart class will be instantiated.
        config: Type-specific configuration dictionary containing chart parameters
            such as traces, layout, positioning, and optional data_source.
            
    Example:
        Plotly line chart configuration:
        
        >>> line_chart = ChartSpec(
        ...     type="plotly_go",
        ...     config={
        ...         "title": "Monthly Revenue",
        ...         "x": 100,
        ...         "y": 150,
        ...         "width": 500,
        ...         "height": 400,
        ...         "traces": [{
        ...             "type": "scatter",
        ...             "x": "$month",
        ...             "y": "$revenue",
        ...             "mode": "lines+markers",
        ...             "name": "Revenue"
        ...         }],
        ...         "data_source": {
        ...             "type": "csv",
        ...             "name": "revenue_data",
        ...             "file_path": "revenue.csv"
        ...         }
        ...     }
        ... )
        
        Custom chart configuration:
        
        >>> custom_chart = ChartSpec(
        ...     type="custom",
        ...     config={
        ...         "chart_fn": "my_visualization_function",
        ...         "chart_config": {
        ...             "style": "minimal",
        ...             "color_scheme": "blue"
        ...         },
        ...         "data_source": {...}
        ...     }
        ... )
        
        Template-based chart configuration:
        
        >>> template_chart = ChartSpec(
        ...     type="template",
        ...     config={
        ...         "template_name": "line_chart",
        ...         "template_config": {
        ...             "x_column": "date",
        ...             "y_column": "value",
        ...             "title": "Trend Analysis"
        ...         }
        ...     }
        ... )
    """
    
    model_config = ConfigDict(extra = "forbid")
    
    type: Annotated[str, Field(..., description = "Chart type: plotly_go or custom")]
    config: Annotated[Dict[str, Any], Field(..., description = "Chart configuration including data_source")]

class SlideSpec(BaseModel):
    """Configuration specification for individual slides in presentations.
    
    This model defines the content and layout for a single slide within a
    presentation. Each slide can contain multiple text replacements and charts,
    which are processed during presentation generation to create the final
    slide content.
    
    The slide specification maps to slides in the presentation template,
    using the ID to identify which template slide should be modified with
    the specified content.
    
    Attributes:
        id: Platform-specific identifier that matches a slide in the presentation
            template (e.g., Google Slides slide ID).
        title: Optional human-readable title for documentation and debugging
            purposes. Not displayed in the actual presentation.
        replacements: List of text replacement specifications that define how
            placeholders in the slide template should be replaced with content.
        charts: List of chart specifications that define visualizations to
            generate and insert into the slide.
            
    Example:
        Complete slide configuration:
        
        >>> slide = SlideSpec(
        ...     id="slide_overview",
        ...     title="Executive Summary",
        ...     replacements=[
        ...         ReplacementSpec(
        ...             type="text",
        ...             config={"placeholder": "{{QUARTER}}", "value": "Q4"}
        ...         ),
        ...         ReplacementSpec(
        ...             type="ai_text",
        ...             config={
        ...                 "placeholder": "{{KEY_INSIGHTS}}",
        ...                 "prompt": "Generate 3 key insights from the data",
        ...                 "data_source": {...}
        ...             }
        ...         )
        ...     ],
        ...     charts=[
        ...         ChartSpec(
        ...             type="plotly_go",
        ...             config={
        ...                 "title": "Revenue Trend",
        ...                 "traces": [...],
        ...                 "x": 50, "y": 100, "width": 400, "height": 300
        ...             }
        ...         ),
        ...         ChartSpec(
        ...             type="plotly_go",
        ...             config={
        ...                 "title": "Market Share",
        ...                 "traces": [...],
        ...                 "x": 500, "y": 100, "width": 200, "height": 200
        ...             }
        ...         )
        ...     ]
        ... )
        
        Minimal slide with only text replacements:
        
        >>> simple_slide = SlideSpec(
        ...     id="slide_title",
        ...     replacements=[
        ...         ReplacementSpec(
        ...             type="text",
        ...             config={"placeholder": "{{TITLE}}", "value": "Annual Report"}
        ...         )
        ...     ]
        ... )
    """
    
    model_config = ConfigDict(extra = "forbid")
    
    id: Annotated[str, Field(..., description = "Slide ID in the Google Slides template")]
    title: Annotated[Optional[str], Field(None, description = "Slide title for documentation")]
    replacements: Annotated[List[ReplacementSpec], Field(default_factory = list, description = "Text replacements for this slide")]
    charts: Annotated[List[ChartSpec], Field(default_factory = list, description = "Charts to generate for this slide")]

class PresentationSpec(BaseModel):
    """Configuration specification for complete presentation content.
    
    This model defines the overall structure and content of a presentation,
    including metadata and the collection of slides that make up the
    presentation. It serves as the container for all slide-level configurations
    and provides the presentation-wide settings.
    
    The presentation specification works with presentation templates to define
    what content should be inserted where, without being tied to any specific
    presentation platform.
    
    Attributes:
        name: Human-readable name for the presentation that will be used as
            the presentation title in the target platform.
        slides: Ordered list of slide specifications that define the content
            and layout for each slide in the presentation.
            
    Example:
        Complete presentation specification:
        
        >>> presentation = PresentationSpec(
        ...     name="Q4 2024 Financial Report",
        ...     slides=[
        ...         SlideSpec(
        ...             id="title_slide",
        ...             title="Title Slide",
        ...             replacements=[
        ...                 ReplacementSpec(
        ...                     type="text",
        ...                     config={"placeholder": "{{PERIOD}}", "value": "Q4 2024"}
        ...                 )
        ...             ]
        ...         ),
        ...         SlideSpec(
        ...             id="overview_slide",
        ...             title="Executive Overview",
        ...             replacements=[...],
        ...             charts=[
        ...                 ChartSpec(
        ...                     type="plotly_go",
        ...                     config={"title": "Revenue Summary", ...}
        ...                 )
        ...             ]
        ...         ),
        ...         SlideSpec(
        ...             id="details_slide",
        ...             title="Detailed Analysis",
        ...             charts=[
        ...                 ChartSpec(type="custom", config={...}),
        ...                 ChartSpec(type="template", config={...})
        ...             ]
        ...         )
        ...     ]
        ... )
        
        Minimal presentation:
        
        >>> simple_presentation = PresentationSpec(
        ...     name="Weekly Update",
        ...     slides=[
        ...         SlideSpec(
        ...             id="main_slide",
        ...             replacements=[
        ...                 ReplacementSpec(
        ...                     type="text",
        ...                     config={"placeholder": "{{DATE}}", "value": "2024-03-15"}
        ...                 )
        ...             ]
        ...         )
        ...     ]
        ... )
    """
    
    model_config = ConfigDict(extra = "forbid")
    
    name: Annotated[str, Field(..., description = "Presentation name")]
    slides: Annotated[List[SlideSpec], Field(..., description = "List of slides in the presentation")]

class ProviderConfig(BaseModel):
    """Configuration for presentation platform providers.
    
    This model defines how to connect to and configure different presentation
    platforms such as Google Slides, PowerPoint, or custom presentation systems.
    It uses a type-based approach where the provider type determines which
    concrete provider class will be instantiated.
    
    The configuration structure allows for platform-specific settings while
    maintaining a consistent interface across different presentation providers.
    Each provider type has its own configuration schema defined in the
    provider-specific configuration classes.
    
    Attributes:
        type: Provider type identifier that determines which presentation
            provider will be used (google_slides, powerpoint, etc.).
        config: Provider-specific configuration dictionary containing all
            parameters needed by the chosen provider implementation.
            
    Example:
        Google Slides provider configuration:
        
        >>> google_config = ProviderConfig(
        ...     type="google_slides",
        ...     config={
        ...         "credentials_path": "/secure/service_account.json",
        ...         "template_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        ...         "drive_folder_id": "1FolderID_for_images",
        ...         "share_with": ["team@company.com"],
        ...         "share_role": "reader"
        ...     }
        ... )
        
        Custom provider configuration:
        
        >>> custom_config = ProviderConfig(
        ...     type="my_custom_provider",
        ...     config={
        ...         "api_endpoint": "https://api.mypresentation.com",
        ...         "api_key": "secret_key_123",
        ...         "workspace_id": "workspace_456",
        ...         "custom_setting": "value"
        ...     }
        ... )
        
        Development/testing configuration:
        
        >>> test_config = ProviderConfig(
        ...     type="mock_provider",
        ...     config={
        ...         "output_directory": "/tmp/presentations",
        ...         "format": "pdf"
        ...     }
        ... )
    """
    
    model_config = ConfigDict(extra = "forbid")
    
    type: Annotated[str, Field(..., description = "Provider type: 'google_slides', 'powerpoint', etc.")]
    config: Annotated[Dict[str, Any], Field(..., description = "Provider-specific configuration")]

class PresentationConfig(BaseModel):
    """Root configuration model for complete presentation generation.
    
    This is the top-level configuration model that contains all necessary
    information to build a presentation from start to finish. It combines
    the presentation content specification with provider configuration and
    system-wide settings.
    
    The configuration is typically loaded from YAML files through the
    ConfigLoader system, which handles template resolution, function execution,
    and parameter substitution before creating this validated configuration
    object.
    
    Attributes:
        presentation: Complete specification of the presentation content
            including all slides, charts, and text replacements.
        provider: Configuration for the presentation platform provider
            that will handle the actual presentation creation and management.
        template_paths: Optional list of custom directories to search for
            chart templates, in priority order. If not specified, only
            built-in templates will be available.
            
    Example:
        Complete presentation configuration:
        
        >>> config = PresentationConfig(
        ...     presentation=PresentationSpec(
        ...         name="Monthly Business Review",
        ...         slides=[
        ...             SlideSpec(
        ...                 id="title",
        ...                 replacements=[...]
        ...             ),
        ...             SlideSpec(
        ...                 id="metrics",
        ...                 charts=[...],
        ...                 replacements=[...]
        ...             ),
        ...             SlideSpec(
        ...                 id="summary",
        ...                 replacements=[...]
        ...             )
        ...         ]
        ...     ),
        ...     provider=ProviderConfig(
        ...         type="google_slides",
        ...         config={
        ...             "credentials_path": "/secure/creds.json",
        ...             "template_id": "presentation_template_123"
        ...         }
        ...     ),
        ...     template_paths=[
        ...         "/custom/chart_templates",
        ...         "/shared/templates"
        ...     ]
        ... )
        
        Minimal configuration:
        
        >>> minimal_config = PresentationConfig(
        ...     presentation=PresentationSpec(
        ...         name="Simple Report",
        ...         slides=[
        ...             SlideSpec(id="main", replacements=[...])
        ...         ]
        ...     ),
        ...     provider=ProviderConfig(
        ...         type="google_slides",
        ...         config={"credentials_path": "/path/to/creds.json"}
        ...     )
        ... )
        
    Usage:
        The configuration is typically used with PresentationBuilder:
        
        >>> from slideflow.presentations.builder import PresentationBuilder
        >>> 
        >>> # Load from YAML
        >>> presentation = PresentationBuilder.from_yaml(
        ...     yaml_path=Path("config.yaml"),
        ...     params={"month": "March"}
        ... )
        >>> 
        >>> # Or from configuration object
        >>> presentation = PresentationBuilder.from_config(config)
        >>> result = presentation.render()
    """
    
    model_config = ConfigDict(extra = "forbid")
    
    presentation: Annotated[PresentationSpec, Field(..., description = "Presentation specification")]
    provider: Annotated[ProviderConfig, Field(..., description = "Presentation provider configuration")]
    template_paths: Annotated[Optional[List[str]], Field(None, description = "Custom template search paths (in priority order)")]
