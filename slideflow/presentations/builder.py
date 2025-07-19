"""Builder pattern implementation for constructing presentations from configuration.

This module provides the PresentationBuilder factory class that handles the
construction of Presentation objects from YAML configuration files or pre-validated
configuration objects. It integrates with the ConfigLoader system to support
template resolution, function registration, and parameter substitution.

The builder pattern separates the complex construction logic from the presentation
objects themselves, providing a clean interface for creating presentations with
all their components including slides, charts, replacements, and data sources.

Key Features:
    - YAML-based presentation configuration with template support
    - Function registry integration for dynamic content generation
    - Parameter substitution for configuration reusability
    - Automatic validation and type conversion using Pydantic
    - Support for custom template paths and providers

Example:
    Creating a presentation from YAML configuration:
    
    >>> from pathlib import Path
    >>> from slideflow.presentations.builder import PresentationBuilder
    >>> 
    >>> # Build from YAML with parameters
    >>> presentation = PresentationBuilder.from_yaml(
    ...     yaml_path=Path("config/monthly_report.yaml"),
    ...     registry_paths=[Path("functions/custom.py")],
    ...     params={"month": "March", "year": "2024"}
    ... )
    >>> 
    >>> # Render the presentation
    >>> result = presentation.render()
    >>> print(f"Created: {result.presentation_url}")

The builder handles:
    - Configuration loading and validation
    - Provider instantiation based on configuration
    - Slide construction with all content elements
    - Replacement and chart object creation
    - Data source configuration and instantiation
"""

from pathlib import Path
from pydantic import TypeAdapter
from typing import Dict, Any, List, Optional

from slideflow.utilities.logging import get_logger
from slideflow.utilities.config import ConfigLoader
from slideflow.replacements import ReplacementUnion
from slideflow.presentations.charts import ChartUnion
from slideflow.data.connectors import DataSourceConfig
from slideflow.presentations.base import Presentation, Slide
from slideflow.presentations.config import PresentationConfig
from slideflow.presentations.providers import ProviderFactory
from slideflow.builtins.template_engine import set_template_paths

logger = get_logger(__name__)

class PresentationBuilder:
    """Factory class for building presentations from configuration.
    
    This builder provides a high-level interface for constructing Presentation
    objects from YAML configuration files or pre-validated configuration objects.
    It handles all the complexity of parsing configurations, resolving templates
    and functions, instantiating providers, and building the complete object
    hierarchy needed for presentation rendering.
    
    The builder pattern allows for:
    - Separation of construction logic from business logic
    - Flexible configuration formats with validation
    - Reusable presentation templates with parameters
    - Integration with custom function registries
    - Support for multiple presentation providers
    
    Example:
        Building from YAML configuration:
        
        >>> # monthly_report.yaml:
        >>> # provider:
        >>> #   type: google_slides
        >>> #   config:
        >>> #     credentials_path: /path/to/creds.json
        >>> # presentation:
        >>> #   name: "{{month}} Report"
        >>> #   slides:
        >>> #     - id: slide_1
        >>> #       title: Overview
        >>> #       replacements:
        >>> #         - type: text
        >>> #           placeholder: "{{MONTH}}"
        >>> #           value: "{{month}}"
        >>> 
        >>> presentation = PresentationBuilder.from_yaml(
        ...     Path("monthly_report.yaml"),
        ...     params={"month": "March"}
        ... )
        >>> result = presentation.render()
        
        Building from configuration object:
        
        >>> from slideflow.presentations.config import PresentationConfig
        >>> 
        >>> config = PresentationConfig(...)
        >>> presentation = PresentationBuilder.from_config(config)
    """
    
    @classmethod
    def from_yaml(
        cls, 
        yaml_path: Path, 
        registry_paths: Optional[List[Path]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> Presentation:
        """Build a presentation from YAML configuration file.
        
        Loads and processes a YAML configuration file using the ConfigLoader system,
        which handles template resolution, function execution, and parameter
        substitution. The resulting configuration is validated and used to construct
        a complete Presentation object ready for rendering.
        
        The YAML file should contain:
        - Provider configuration for the presentation platform
        - Presentation metadata including name and slides
        - Slide definitions with replacements and charts
        - Optional template paths and other settings
        
        Args:
            yaml_path: Path to the YAML configuration file containing presentation
                definition. The file must be readable and contain valid YAML.
            registry_paths: Optional list of Python files containing custom functions
                for use in templates. Functions in these files can be referenced
                using the `!func` tag in YAML.
            params: Optional dictionary of parameters for template substitution.
                These values replace `{{parameter}}` placeholders in the YAML.
                
        Returns:
            Fully constructed Presentation object with all slides, charts,
            replacements, and provider configuration ready for rendering.
            
        Raises:
            FileNotFoundError: If yaml_path doesn't exist or isn't readable.
            YAMLError: If the YAML file contains syntax errors.
            ValidationError: If the configuration doesn't match expected schema.
            ConfigurationError: If required configuration elements are missing.
            
        Example:
            >>> # config/report.yaml:
            >>> # provider:
            >>> #   type: google_slides
            >>> #   config:
            >>> #     credentials_path: "{{CREDS_PATH}}"
            >>> # presentation:
            >>> #   name: "Q{{quarter}} {{year}} Report"
            >>> #   slides:
            >>> #     - id: slide_1
            >>> #       replacements:
            >>> #         - type: ai_text
            >>> #           placeholder: "{{SUMMARY}}"
            >>> #           prompt: !func generate_summary
            >>> 
            >>> presentation = PresentationBuilder.from_yaml(
            ...     yaml_path=Path("config/report.yaml"),
            ...     registry_paths=[Path("functions.py")],
            ...     params={
            ...         "CREDS_PATH": "/secure/creds.json",
            ...         "quarter": "4",
            ...         "year": "2024"
            ...     }
            ... )
        """
        loader = ConfigLoader(
            yaml_path = yaml_path,
            registry_paths = registry_paths or [],
            params = params or {}
        )
        
        resolved_config = loader.config
        config = PresentationConfig.model_validate(resolved_config)

        return cls.from_config(config)
    
    @classmethod
    def from_config(cls, config: PresentationConfig) -> Presentation:
        """Build a presentation from a validated configuration object.
        
        Constructs a complete Presentation object from a pre-validated
        PresentationConfig instance. This method handles the instantiation
        of all components including the provider, slides, charts, replacements,
        and data sources based on the configuration.
        
        This method is useful when:
        - Working with programmatically generated configurations
        - Implementing custom configuration loading logic
        - Testing with mock configurations
        - Avoiding repeated YAML parsing for the same configuration
        
        Args:
            config: Validated PresentationConfig object containing all necessary
                configuration for building the presentation. All templates and
                functions should already be resolved.
                
        Returns:
            Fully constructed Presentation object ready for rendering operations.
            
        Raises:
            ConfigurationError: If provider type is not supported or configuration
                is invalid for the specified provider.
            ValidationError: If any component configuration fails validation.
            
        Example:
            >>> from slideflow.presentations.config import PresentationConfig
            >>> from slideflow.presentations.config import PresentationSpec
            >>> from slideflow.presentations.config import SlideSpec
            >>> 
            >>> # Create configuration programmatically
            >>> config = PresentationConfig(
            ...     provider=ProviderConfig(
            ...         type="google_slides",
            ...         config={"credentials_path": "/path/to/creds.json"}
            ...     ),
            ...     presentation=PresentationSpec(
            ...         name="Programmatic Presentation",
            ...         slides=[
            ...             SlideSpec(
            ...                 id="slide_1",
            ...                 title="Title Slide",
            ...                 replacements=[...],
            ...                 charts=[...]
            ...             )
            ...         ]
            ...     )
            ... )
            >>> 
            >>> # Build presentation
            >>> presentation = PresentationBuilder.from_config(config)
            >>> result = presentation.render()
        """
        if config.template_paths:
            set_template_paths(config.template_paths)

        provider = ProviderFactory.create_provider(config.provider)

        slides = []
        for slide_spec in config.presentation.slides:
            slide = cls._build_slide(slide_spec)
            slides.append(slide)
        
        presentation = Presentation(
            name = config.presentation.name,
            slides = slides,
            provider = provider
        )
        
        return presentation
    
    @classmethod
    def _build_slide(cls, spec) -> Slide:
        """Build a slide from its specification with all content elements.
        
        Constructs a Slide object by processing the slide specification and
        building all associated replacements and charts. This method handles
        the recursive construction of nested components.
        
        Args:
            spec: SlideSpec object containing the slide configuration including
                ID, title, and lists of replacement and chart specifications.
                All functions should already be resolved by ConfigLoader.
                
        Returns:
            Fully constructed Slide object with all replacements and charts
            instantiated and ready for rendering.
            
        Example:
            The method processes specifications like:
            >>> slide_spec = SlideSpec(
            ...     id="slide_1",
            ...     title="Overview",
            ...     replacements=[replacement_spec1, replacement_spec2],
            ...     charts=[chart_spec1, chart_spec2]
            ... )
            >>> slide = PresentationBuilder._build_slide(slide_spec)
        """
        replacements = []
        for repl_spec in spec.replacements:
            replacement = cls._build_replacement(repl_spec)
            replacements.append(replacement)
        
        charts = []
        for chart_spec in spec.charts:
            chart = cls._build_chart(chart_spec)
            charts.append(chart)
        
        return Slide(
            id = spec.id,
            title = spec.title,
            replacements = replacements,
            charts = charts
        )
    
    @classmethod
    def _build_replacement(cls, spec) -> ReplacementUnion:
        """Build a replacement object from its specification.
        
        Constructs the appropriate replacement type based on the specification
        using Pydantic's discriminated union system. This method handles the
        dynamic instantiation of different replacement types (text, ai_text,
        table, etc.) based on the type field in the specification.
        
        The method also handles nested data source construction when a replacement
        requires data from an external source.
        
        Args:
            spec: ReplacementSpec object containing the replacement type and
                configuration. All template functions should be pre-resolved.
                
        Returns:
            Concrete replacement instance (TextReplacement, AITextReplacement,
            TableReplacement, etc.) based on the specification type.
            
        Raises:
            ValidationError: If the replacement type is unknown or configuration
                doesn't match the expected schema for that type.
                
        Example:
            >>> # Text replacement spec
            >>> text_spec = ReplacementSpec(
            ...     type="text",
            ...     config={
            ...         "placeholder": "{{COMPANY}}",
            ...         "value": "Acme Corp"
            ...     }
            ... )
            >>> replacement = PresentationBuilder._build_replacement(text_spec)
            >>> 
            >>> # Table replacement with data source
            >>> table_spec = ReplacementSpec(
            ...     type="table",
            ...     config={
            ...         "prefix": "SALES_",
            ...         "data_source": {"type": "csv", "name": "sales", "file_path": "data.csv"}
            ...     }
            ... )
            >>> replacement = PresentationBuilder._build_replacement(table_spec)
        """
        config = spec.config.copy()

        data_source_config = config.pop('data_source', None)
        if data_source_config:
            data_source = cls._build_data_source(data_source_config)
            config['data_source'] = data_source
        
        # Add type to config and let Pydantic discriminated union handle the rest
        config['type'] = spec.type
        
        # Use TypeAdapter to validate and construct the correct replacement type
        adapter = TypeAdapter(ReplacementUnion)
        return adapter.validate_python(config)
    
    @classmethod
    def _build_chart(cls, spec) -> ChartUnion:
        """Build a chart object from its specification.
        
        Constructs the appropriate chart type based on the specification using
        Pydantic's discriminated union system. This method handles the dynamic
        instantiation of different chart types (line, bar, scatter, etc.) and
        manages associated data source construction.
        
        The method extracts positioning, styling, and data configuration from
        the specification to create a fully configured chart ready for rendering.
        
        Args:
            spec: ChartSpec object containing the chart type and configuration
                including positioning, data source, and visualization parameters.
                All template functions should be pre-resolved.
                
        Returns:
            Concrete chart instance (LineChart, BarChart, ScatterChart, etc.)
            based on the specification type, fully configured for rendering.
            
        Raises:
            ValidationError: If the chart type is unknown or configuration
                doesn't match the expected schema for that type.
                
        Example:
            >>> # Line chart spec
            >>> line_spec = ChartSpec(
            ...     type="line",
            ...     config={
            ...         "title": "Monthly Revenue",
            ...         "x": 50,
            ...         "y": 100,
            ...         "width": 400,
            ...         "height": 300,
            ...         "x_column": "month",
            ...         "y_columns": ["revenue"],
            ...         "data_source": {
            ...             "type": "databricks",
            ...             "name": "revenue_data",
            ...             "query": "SELECT month, revenue FROM metrics"
            ...         }
            ...     }
            ... )
            >>> chart = PresentationBuilder._build_chart(line_spec)
        """
        config = spec.config.copy()

        data_source_config = config.pop('data_source', None)
        if data_source_config:
            data_source = cls._build_data_source(data_source_config)
            config['data_source'] = data_source
        
        # Add type to config and let Pydantic discriminated union handle the rest
        config['type'] = spec.type
        
        # Use TypeAdapter to validate and construct the correct chart type
        adapter = TypeAdapter(ChartUnion)
        return adapter.validate_python(config)
    
    @classmethod
    def _build_data_source(cls, config: Dict[str, Any]):
        """Build a data source configuration from dictionary specification.
        
        Constructs the appropriate data source type (CSV, JSON, Databricks, DBT)
        based on the configuration dictionary. This method uses Pydantic's
        discriminated union system to validate and instantiate the correct
        data source type.
        
        Data sources are used by charts and replacements to fetch data from
        external systems. Each data source type has its own configuration
        requirements and connection parameters.
        
        Args:
            config: Dictionary containing data source configuration with at
                minimum a 'type' field specifying the data source type
                (csv, json, databricks, dbt) and type-specific parameters.
                
        Returns:
            Concrete DataSourceConfig instance (CSVDataSource, JSONDataSource,
            DatabricksDataSource, DBTDataSource) based on the type field.
            
        Raises:
            ValidationError: If the data source type is unknown or required
                configuration parameters are missing or invalid.
                
        Example:
            >>> # CSV data source
            >>> csv_config = {
            ...     "type": "csv",
            ...     "name": "sales_data",
            ...     "file_path": "/data/sales.csv"
            ... }
            >>> data_source = PresentationBuilder._build_data_source(csv_config)
            >>> 
            >>> # Databricks data source
            >>> databricks_config = {
            ...     "type": "databricks",
            ...     "name": "metrics",
            ...     "query": "SELECT * FROM monthly_metrics WHERE year = 2024"
            ... }
            >>> data_source = PresentationBuilder._build_data_source(databricks_config)
        """
        adapter = TypeAdapter(DataSourceConfig)
        return adapter.validate_python(config)
