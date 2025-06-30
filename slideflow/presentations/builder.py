from pathlib import Path
from pydantic import TypeAdapter
from typing import Dict, Any, List, Optional

from slideflow.utilities.config import ConfigLoader
from slideflow.replacements import ReplacementUnion
from slideflow.presentations.charts import ChartUnion
from slideflow.presentations.base import Presentation, Slide
from slideflow.presentations.config import PresentationConfig
from slideflow.presentations.providers import ProviderFactory
from slideflow.builtins.template_engine import set_template_paths
from slideflow.data.connectors import DataSourceConfig
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

class PresentationBuilder:
    """Factory for building presentations using ConfigLoader."""
    
    @classmethod
    def from_yaml(
        cls, 
        yaml_path: Path, 
        registry_paths: Optional[List[Path]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> Presentation:
        """Build presentation from YAML configuration using ConfigLoader.
        
        Args:
            yaml_path: Path to YAML configuration file
            registry_paths: List of paths to function registry files
            params: Parameters for template substitution
            
        Returns:
            Built Presentation instance
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
        """Build presentation from already-resolved configuration.
        
        Args:
            config: Presentation configuration (functions already resolved)
            
        Returns:
            Built Presentation instance
        """
        # Set custom template paths if provided
        if config.template_paths:
            set_template_paths(config.template_paths)
        
        # Create presentation provider
        provider = ProviderFactory.create_provider(config.provider)
        
        # Build slides from specs
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
        """Build slide with replacements and charts.
        
        Args:
            spec: Slide specification (already resolved by ConfigLoader)
            
        Returns:
            Built Slide instance
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
        """Build replacement from specification using Pydantic discriminated unions.
        
        Args:
            spec: Replacement specification (functions already resolved)
            
        Returns:
            Built replacement instance
        """
        config = spec.config.copy()
        
        # Extract and build data source if present
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
        """Build chart from specification using Pydantic discriminated unions.
        
        Args:
            spec: Chart specification (functions already resolved)
            
        Returns:
            Built chart instance
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
        """Build data source configuration from dict.
        
        Args:
            config: Data source configuration dict
            
        Returns:
            Built DataSourceConfig instance
        """
        adapter = TypeAdapter(DataSourceConfig)
        return adapter.validate_python(config)
