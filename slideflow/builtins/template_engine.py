"""YAML-based template engine with Jinja2 support for Slideflow.

This module provides a flexible template system for generating chart configurations
and other presentation components using YAML files with Jinja2 templating.
It supports parameter validation, custom filters, and multi-directory template
discovery.

The template engine is designed to:
    - Process YAML templates with embedded Jinja2 syntax
    - Validate template parameters with type checking
    - Provide reusable custom filters for common operations
    - Support multiple template search directories
    - Cache loaded templates for performance

Template Structure:
    Templates are YAML files with two sections:
    1. Metadata: Template information and parameter definitions
    2. Template: Jinja2-enabled YAML content

Example Template File::

    name: "Basic Table"
    description: "Simple table with dynamic columns"
    version: "1.0"
    parameters:
      - name: columns
        type: list
        required: true
        description: "List of column names"
      - name: title
        type: str
        required: false
        default: "Data Table"
        description: "Table title"
    
    template: |
      type: plotly_go
      config:
        traces:
          - type: Table
            header:
              values: {{ columns | list }}
            cells:
              values: [{% for col in columns %}${{ col }}{% if not loop.last %}, {% endif %}{% endfor %}]
        layout:
          title: "{{ title }}"

Classes:
    TemplateParameter: Definition of a template parameter with validation
    ChartTemplate: Complete template definition loaded from YAML
    TemplateEngine: Main engine for loading, validating, and rendering templates

Functions:
    get_template_engine: Get the global template engine instance
    set_template_paths: Configure custom template search paths
    reset_template_engine: Reset to default configuration
"""

import yaml
from pathlib import Path
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Union
from jinja2 import Environment, BaseLoader, select_autoescape

from slideflow.utilities.exceptions import ChartGenerationError

class TemplateParameter(BaseModel):
    """Definition of a template parameter with validation rules.
    
    Represents a single parameter that can be passed to a template,
    including its type, default value, and validation requirements.
    
    Attributes:
        name: Unique identifier for the parameter.
        type: Expected parameter type (e.g., 'str', 'int', 'list', 'dict').
        required: Whether this parameter must be provided by the user.
        default: Default value used when parameter is not provided and not required.
        description: Human-readable description of the parameter's purpose.
        
    Example:
        >>> param = TemplateParameter(
        ...     name="columns",
        ...     type="list", 
        ...     required=True,
        ...     description="List of column names to display"
        ... )
    """
    name: str
    type: str
    required: bool = True
    default: Any = None
    description: str = ""

class ChartTemplate(BaseModel):
    """Complete template definition loaded from YAML file.
    
    Represents a fully parsed template including metadata, parameters,
    and the Jinja2 template content ready for rendering.
    
    Attributes:
        name: Human-readable name of the template.
        description: Detailed description of the template's purpose and usage.
        version: Template version for compatibility tracking.
        parameters: List of parameter definitions for validation.
        template: Raw Jinja2 template text to be rendered.
        filters: Optional custom filters specific to this template.
        
    Example:
        >>> template = ChartTemplate(
        ...     name="Sales Dashboard",
        ...     description="Monthly sales performance table",
        ...     version="2.1",
        ...     parameters=[...],
        ...     template="type: plotly_go\nconfig: ..."
        ... )
    """
    name: str
    description: str
    version: str = "1.0"
    parameters: List[TemplateParameter]
    template: str  # Raw template text for Jinja2 processing
    filters: Optional[Dict[str, str]] = None

class TemplateEngine:
    """Engine for processing YAML templates with Jinja2 support.
    
    The TemplateEngine provides a complete template processing system that:
    - Loads templates from multiple search directories
    - Validates template parameters against schemas
    - Renders templates using Jinja2 with custom filters
    - Caches loaded templates for performance
    - Provides introspection capabilities
    
    The engine supports a hierarchical template discovery system where
    templates in earlier directories take priority over later ones.
    
    Attributes:
        template_paths: List of directories searched for templates (in priority order).
        
    Example:
        >>> engine = TemplateEngine(["/project/templates", "/shared/templates"])
        >>> config = engine.render_template("sales_table", {
        ...     "columns": ["product", "revenue", "growth"],
        ...     "title": "Q3 Sales Report"
        ... })
    """
    
    def __init__(self, template_paths: Optional[List[Union[str, Path]]] = None):
        """Initialize the template engine with search paths and filters.
        
        Args:
            template_paths: List of directories to search for templates (in priority order).
                If None, uses default discovery paths:
                1. ./templates/ (current working directory)
                2. ~/.slideflow/templates/ (user home directory)
                Only existing directories are included in the search.
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
        """Configure custom Jinja2 filters for template processing.
        
        Registers a comprehensive set of filters that can be used in templates
        for common data transformation, formatting, and presentation tasks.
        All filters are designed to be generic and reusable across different
        template types.
        
        Filter Categories:
            - String transformations: title_case, snake_to_kebab, add_prefix
            - List operations: enumerate_list, zip_lists, repeat_value
            - Color utilities: alternating_colors, hex_to_rgb, color_reference
            - Conditionals: if_else, default_if_none, contains
            - Chart helpers: chart_alignment, column_width, column_format
            - Math operations: multiply, divide, round_number
        """
        
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
        """Load and parse a template from YAML file.
        
        Searches for the template across all configured template paths,
        parses the YAML structure, validates the format, and caches
        the result for future use.
        
        Args:
            template_name: Name of the template file without the .yml extension.
                Template files must be named '{template_name}.yml'.
                
        Returns:
            Parsed ChartTemplate object containing metadata and template content.
            
        Raises:
            ChartGenerationError: If template file is not found in any search path,
                cannot be parsed as valid YAML, or is missing required sections.
                
        Example:
            >>> engine = TemplateEngine()
            >>> template = engine.load_template("sales_dashboard")
            >>> print(f"{template.name}: {template.description}")
            >>> print(f"Parameters: {[p.name for p in template.parameters]}")
            
        Note:
            - Templates are cached after first load for performance
            - Search paths are checked in priority order
            - Template files must have 'template:' section for Jinja2 content
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
                name = metadata['name'],
                description = metadata['description'],
                version = metadata.get('version', '1.0'),
                parameters = parameters,
                template = template_raw,  # Store as raw text, not parsed YAML
                filters = metadata.get('filters')
            )
            
            self._template_cache[template_name] = template
            return template
            
        except Exception as e:
            raise ChartGenerationError(f"Failed to load template '{template_name}': {e}")
    
    def render_template(self, template_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Render a template with provided configuration parameters.
        
        Loads the specified template, validates the provided configuration
        against the template's parameter schema, applies defaults for missing
        optional parameters, and renders the template using Jinja2.
        
        Args:
            template_name: Name of the template to render (without .yml extension).
            config: Dictionary of parameter values to pass to the template.
                Keys must match parameter names defined in the template.
                
        Returns:
            Dictionary containing the rendered template output. The structure
            depends on the template content but typically contains chart
            configuration or presentation component definitions.
            
        Raises:
            ChartGenerationError: If template is not found, required parameters
                are missing, parameter validation fails, or Jinja2 rendering
                encounters errors.
                
        Example:
            >>> engine = TemplateEngine()
            >>> chart_config = engine.render_template(
            ...     "sales_table",
            ...     {
            ...         "columns": ["product", "revenue", "growth"],
            ...         "title": "Q3 Performance",
            ...         "show_totals": True
            ...     }
            ... )
            >>> print(chart_config["type"])  # 'plotly_go'
            
        Note:
            - All required parameters must be provided in config
            - Optional parameters use their default values if not provided
            - Rendered output is parsed from YAML to Python dictionary
        """
        template = self.load_template(template_name)
        
        # Validate and apply defaults to config
        validated_config = self._validate_config(template, config)

        try:
            template_text = template.template

            jinja_template = self._jinja_env.from_string(template_text)
            
            rendered_yaml = jinja_template.render(**validated_config)

            rendered_config = yaml.safe_load(rendered_yaml)
            
            return rendered_config
            
        except Exception as e:
            raise ChartGenerationError(f"Failed to render template '{template_name}': {e}")
    
    def _validate_config(self, template: ChartTemplate, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user configuration against template parameter schema.
        
        Checks that all required parameters are provided, applies default
        values for optional parameters, and ensures the configuration
        is complete for template rendering.
        
        Args:
            template: The loaded template containing parameter definitions.
            config: User-provided configuration dictionary.
            
        Returns:
            Validated and complete configuration dictionary with defaults applied.
            
        Raises:
            ChartGenerationError: If required parameters are missing.
            
        Note:
            - Type validation is currently limited to presence checking
            - Future versions may include more sophisticated type validation
        """
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
        """List all available template names across all search paths.
        
        Scans all configured template directories and returns the names
        of all available template files. If multiple directories contain
        templates with the same name, only the highest priority one
        (first in search path) is listed.
        
        Returns:
            Sorted list of template names (without .yml extension) that
            can be used with load_template() or render_template().
            
        Example:
            >>> engine = TemplateEngine()
            >>> templates = engine.list_templates()
            >>> print(f"Available templates: {templates}")
            >>> for name in templates:
            ...     info = engine.get_template_info(name)
            ...     print(f"  {name}: {info['description']}")
        """
        template_names = set()
        
        for templates_dir in self.template_paths:
            if templates_dir.exists():
                for template_file in templates_dir.glob("*.yml"):
                    if template_file.is_file():
                        template_names.add(template_file.stem)
        
        return sorted(list(template_names))
    
    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """Get detailed information about a template.
        
        Loads the template and returns its metadata including parameter
        definitions, which can be used for documentation, validation,
        or building user interfaces.
        
        Args:
            template_name: Name of the template to inspect.
            
        Returns:
            Dictionary containing template metadata:
                - name: Human-readable template name
                - description: Template description
                - version: Template version string
                - parameters: List of parameter definitions with details
                
        Raises:
            ChartGenerationError: If template cannot be found or loaded.
            
        Example:
            >>> engine = TemplateEngine()
            >>> info = engine.get_template_info("sales_table")
            >>> print(f"Template: {info['name']} v{info['version']}")
            >>> print(f"Description: {info['description']}")
            >>> for param in info['parameters']:
            ...     required = "*" if param['required'] else ""
            ...     print(f"  {param['name']}{required}: {param['description']}")
        """
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
    """Get the global template engine instance.
    
    Returns a singleton TemplateEngine instance that is shared across
    the application. The instance is created with default settings
    on first access.
    
    Returns:
        The global TemplateEngine instance.
        
    Example:
        >>> engine = get_template_engine()
        >>> templates = engine.list_templates()
        >>> config = engine.render_template("my_template", {...})
        
    Note:
        - Uses lazy initialization - created on first call
        - Subsequent calls return the same instance
        - Use set_template_paths() to configure custom paths
    """
    global _template_engine
    if _template_engine is None:
        _template_engine = TemplateEngine()
    return _template_engine

def set_template_paths(template_paths: List[Union[str, Path]]) -> None:
    """Configure custom template search paths for the global engine.
    
    Replaces the global template engine with a new instance that uses
    the specified search paths. This affects all subsequent template
    operations throughout the application.
    
    Args:
        template_paths: List of directories to search for templates, in
            priority order. Earlier paths take precedence over later ones.
            Non-existent directories are automatically filtered out.
            
    Example:
        >>> # Set custom template paths
        >>> set_template_paths([
        ...     "/project/custom_templates",
        ...     "/shared/org_templates",
        ...     Path.home() / ".slideflow" / "templates"
        ... ])
        >>> 
        >>> # Now all template operations use these paths
        >>> engine = get_template_engine()
        >>> templates = engine.list_templates()
        
    Note:
        - Resets the global template engine, clearing any cached templates
        - Affects all subsequent calls to get_template_engine()
        - Use reset_template_engine() to return to default paths
    """
    global _template_engine
    _template_engine = TemplateEngine(template_paths=template_paths)

def reset_template_engine() -> None:
    """Reset the global template engine to default configuration.
    
    Clears the global template engine instance, causing it to be
    recreated with default search paths on next access. This is
    useful for testing or when you want to return to default
    behavior after custom configuration.
    
    Example:
        >>> # After custom configuration
        >>> set_template_paths(["/custom/path"])
        >>> 
        >>> # Reset to defaults
        >>> reset_template_engine()
        >>> 
        >>> # Next call will use default paths
        >>> engine = get_template_engine()
        
    Note:
        - Clears all cached templates
        - Next call to get_template_engine() will create new instance
        - Default paths are ./templates/ and ~/.slideflow/templates/
    """
    global _template_engine
    _template_engine = None
