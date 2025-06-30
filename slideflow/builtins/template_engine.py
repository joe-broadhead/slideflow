"""
YAML-based Template Engine for SlideFlow Builtin Charts

This module provides a scalable way to define chart templates using YAML files
with Jinja2-style templating for dynamic configuration generation.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from jinja2 import Environment, BaseLoader, select_autoescape
from pydantic import BaseModel

from slideflow.utilities.exceptions import ChartGenerationError


class TemplateParameter(BaseModel):
    """Definition of a template parameter."""
    name: str
    type: str
    required: bool = True
    default: Any = None
    description: str = ""


class ChartTemplate(BaseModel):
    """A chart template loaded from YAML."""
    name: str
    description: str
    version: str = "1.0"
    parameters: List[TemplateParameter]
    template: str  # Raw template text for Jinja2 processing
    filters: Optional[Dict[str, str]] = None


class TemplateEngine:
    """Engine for processing YAML chart templates."""
    
    def __init__(self, template_paths: Optional[List[Union[str, Path]]] = None):
        """Initialize the template engine with multiple template search paths.
        
        Args:
            template_paths: List of directories to search for templates (in priority order)
                          If None, uses default discovery paths:
                          1. ./templates/ (user project)
                          2. ~/.slideflow/templates/ (global user)
        """
        if template_paths is None:
            # Default template discovery paths (in priority order)
            template_paths = [
                Path.cwd() / "templates",  # User project templates
                Path.home() / ".slideflow" / "templates",  # Global user templates
            ]
        
        # Convert all paths to Path objects and ensure they exist
        self.template_paths = []
        for path in template_paths:
            path_obj = Path(path)
            if path_obj.exists() and path_obj.is_dir():
                self.template_paths.append(path_obj)
        self._template_cache: Dict[str, ChartTemplate] = {}
        self._jinja_env = Environment(
            loader=BaseLoader(),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
        # Add custom filters
        self._setup_filters()
    
    def _setup_filters(self):
        """Set up generic, reusable Jinja2 filters for template processing."""
        
        # String transformation filters
        def title_case(text: str) -> str:
            """Convert snake_case to Title Case."""
            return text.replace('_', ' ').title()
        
        def snake_to_kebab(text: str) -> str:
            """Convert snake_case to kebab-case."""
            return text.replace('_', '-')
        
        def add_prefix(text: str, prefix: str = '$') -> str:
            """Add prefix to text (e.g., for column references)."""
            return f'{prefix}{text}'
        
        def add_suffix(text: str, suffix: str) -> str:
            """Add suffix to text."""
            return f'{text}{suffix}'
        
        # List/sequence filters
        def enumerate_list(items: List[Any]) -> List[tuple]:
            """Enumerate a list with indices."""
            return list(enumerate(items))
        
        def zip_lists(*lists) -> List[tuple]:
            """Zip multiple lists together."""
            return list(zip(*lists))
        
        def repeat_value(value: Any, count: int) -> List[Any]:
            """Repeat a value N times."""
            return [value] * count
        
        # Color and styling filters
        def alternating_colors(index: int, color1: str = '#f8f9fa', color2: str = 'white') -> List[str]:
            """Generate alternating colors based on index."""
            return [color1] if index % 2 == 0 else [color2]
        
        def color_reference(index: int, prefix: str = '$_color_col_') -> str:
            """Generate color column reference."""
            return f'{prefix}{index}'
        
        def hex_to_rgb(hex_color: str) -> str:
            """Convert hex color to RGB."""
            hex_color = hex_color.lstrip('#')
            return f"rgb({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)})"
        
        # Conditional filters
        def if_else(condition: bool, true_value: Any, false_value: Any) -> Any:
            """Simple ternary operator."""
            return true_value if condition else false_value
        
        def default_if_none(value: Any, default: Any) -> Any:
            """Return default if value is None."""
            return default if value is None else value
        
        def contains(text: str, substring: str) -> bool:
            """Check if text contains substring."""
            return substring.lower() in text.lower()
        
        def starts_with(text: str, prefix: str) -> bool:
            """Check if text starts with prefix."""
            return text.lower().startswith(prefix.lower())
        
        def ends_with(text: str, suffix: str) -> bool:
            """Check if text ends with suffix."""
            return text.lower().endswith(suffix.lower())
        
        # Chart-specific helpers (generic enough for reuse)
        def chart_alignment(column: str, title_column: Optional[str] = None) -> str:
            """Determine text alignment for column."""
            return 'left' if column == title_column else 'center'
        
        def column_width(column: str, width_map: Optional[Dict[str, int]] = None) -> int:
            """Determine column width with configurable mapping."""
            if width_map:
                # Check exact matches first
                if column in width_map:
                    return width_map[column]
                # Check pattern matches
                for pattern, width in width_map.items():
                    if pattern in column.lower():
                        return width
            
            # Simple default - no hardcoded heuristics
            return 80
        
        def column_format(column: str, format_map: Optional[Dict[str, str]] = None) -> Optional[str]:
            """Determine format string for column with configurable mapping."""
            if format_map:
                # Check exact matches first
                if column in format_map:
                    return format_map[column]
                # Check pattern matches
                for pattern, fmt in format_map.items():
                    if pattern in column.lower():
                        return fmt
            
            # No format by default - let template explicitly specify formats
            return None
        
        # Math filters
        def multiply(value: Union[int, float], factor: Union[int, float]) -> Union[int, float]:
            """Multiply value by factor."""
            return value * factor
        
        def divide(value: Union[int, float], divisor: Union[int, float]) -> Union[int, float]:
            """Divide value by divisor."""
            return value / divisor if divisor != 0 else 0
        
        def round_number(value: Union[int, float], digits: int = 0) -> Union[int, float]:
            """Round number to specified digits."""
            return round(value, digits)
        
        # Register all filters
        self._jinja_env.filters.update({
            # String transformations
            'title_case': title_case,
            'snake_to_kebab': snake_to_kebab,
            'add_prefix': add_prefix,
            'add_suffix': add_suffix,
            
            # List operations
            'enumerate_list': enumerate_list,
            'zip_lists': zip_lists,
            'repeat_value': repeat_value,
            
            # Color and styling
            'alternating_colors': alternating_colors,
            'color_reference': color_reference,
            'hex_to_rgb': hex_to_rgb,
            
            # Conditionals
            'if_else': if_else,
            'default_if_none': default_if_none,
            'contains': contains,
            'starts_with': starts_with,
            'ends_with': ends_with,
            
            # Chart helpers
            'chart_alignment': chart_alignment,
            'column_width': column_width,
            'column_format': column_format,
            
            # Math
            'multiply': multiply,
            'divide': divide,
            'round_number': round_number,
        })
    
    def load_template(self, template_name: str) -> ChartTemplate:
        """Load a chart template from YAML file.
        
        Args:
            template_name: Name of the template (without .yml extension)
            
        Returns:
            Loaded chart template
            
        Raises:
            ChartGenerationError: If template file not found or invalid
        """
        if template_name in self._template_cache:
            return self._template_cache[template_name]
        
        # Search for template in all template paths (in priority order)
        template_path = None
        for templates_dir in self.template_paths:
            candidate_path = templates_dir / f"{template_name}.yml"
            if candidate_path.exists():
                template_path = candidate_path
                break
        
        if template_path is None:
            searched_paths = [str(path / f"{template_name}.yml") for path in self.template_paths]
            raise ChartGenerationError(f"Template '{template_name}' not found in any template directory. Searched: {searched_paths}")
        
        try:
            with open(template_path, 'r') as f:
                content = f.read()
            
            # Split the file into metadata and template sections
            # The template section will be stored as raw text for Jinja2 processing
            lines = content.split('\n')
            
            # Find where the template section starts
            template_start = None
            for i, line in enumerate(lines):
                if line.strip() == 'template:':
                    template_start = i
                    break
            
            if template_start is None:
                raise ChartGenerationError("No 'template:' section found in template file")
            
            # Parse the metadata section (everything before template:)
            metadata_yaml = '\n'.join(lines[:template_start])
            metadata = yaml.safe_load(metadata_yaml)
            
            # Store the template section as raw text for Jinja2 processing
            template_lines = lines[template_start + 1:]  # Skip the 'template:' line
            
            # Remove common indentation from template section
            if template_lines:
                # Find minimum indentation (excluding empty lines)
                min_indent = float('inf')
                for line in template_lines:
                    if line.strip():  # Skip empty lines
                        indent = len(line) - len(line.lstrip())
                        min_indent = min(min_indent, indent)
                
                if min_indent != float('inf'):
                    # Remove the common indentation
                    template_lines = [
                        line[min_indent:] if len(line) > min_indent else line
                        for line in template_lines
                    ]
            
            template_raw = '\n'.join(template_lines)
            
            # Parse parameters
            parameters = []
            for param_data in metadata.get('parameters', []):
                parameters.append(TemplateParameter(**param_data))
            
            template = ChartTemplate(
                name=metadata['name'],
                description=metadata['description'],
                version=metadata.get('version', '1.0'),
                parameters=parameters,
                template=template_raw,  # Store as raw text, not parsed YAML
                filters=metadata.get('filters')
            )
            
            self._template_cache[template_name] = template
            return template
            
        except Exception as e:
            raise ChartGenerationError(f"Failed to load template '{template_name}': {e}")
    
    def render_template(self, template_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Render a template with user configuration.
        
        Args:
            template_name: Name of the template to render
            config: User configuration parameters
            
        Returns:
            Rendered chart configuration
            
        Raises:
            ChartGenerationError: If rendering fails
        """
        template = self.load_template(template_name)
        
        # Validate and apply defaults to config
        validated_config = self._validate_config(template, config)
        
        # Render using Jinja2 templating - fully generic, no hardcoding!
        try:
            # Template is already stored as raw text
            template_text = template.template
            
            # Create Jinja2 template
            jinja_template = self._jinja_env.from_string(template_text)
            
            # Render with user config
            rendered_yaml = jinja_template.render(**validated_config)
            
            # Parse rendered YAML to dict
            rendered_config = yaml.safe_load(rendered_yaml)
            
            return rendered_config
            
        except Exception as e:
            raise ChartGenerationError(f"Failed to render template '{template_name}': {e}")
    
    def _validate_config(self, template: ChartTemplate, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user config against template parameters and apply defaults."""
        validated = {}
        
        # Check all parameters
        for param in template.parameters:
            if param.name in config:
                validated[param.name] = config[param.name]
            elif param.required:
                raise ChartGenerationError(f"Required parameter '{param.name}' missing")
            else:
                validated[param.name] = param.default
        
        return validated
    
    
    def list_templates(self) -> List[str]:
        """List all available template names."""
        if not self.templates_dir.exists():
            return []
        
        return [
            f.stem for f in self.templates_dir.glob("*.yml")
            if f.is_file()
        ]
    
    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """Get information about a template including parameters."""
        template = self.load_template(template_name)
        
        return {
            'name': template.name,
            'description': template.description,
            'version': template.version,
            'parameters': [
                {
                    'name': p.name,
                    'type': p.type,
                    'required': p.required,
                    'default': p.default,
                    'description': p.description
                }
                for p in template.parameters
            ]
        }


# Global template engine instance
_template_engine = None


def get_template_engine() -> TemplateEngine:
    """Get the global template engine instance."""
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine

def set_template_paths(template_paths: List[Union[str, Path]]) -> None:
    """Set custom template search paths and reset the global template engine.
    
    Args:
        template_paths: List of directories to search for templates (in priority order)
    """
    global _template_engine
    _template_engine = TemplateEngine(template_paths=template_paths)

def reset_template_engine() -> None:
    """Reset the template engine to use default paths."""
    global _template_engine
    _template_engine = None