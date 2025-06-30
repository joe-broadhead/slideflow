from typing import Optional, Tuple, Union
from operator import add, sub, mul, truediv
from ast import Add, Sub, Mult, Div, parse, Expression, BinOp, Num

from slideflow.utilities.exceptions import ChartGenerationError

def safe_eval_expression(expr: str) -> Union[float, int]:
    """
    Safely evaluates a basic arithmetic expression using the AST module.

    Supports only basic binary operations: addition (+), subtraction (-),
    multiplication (*), and division (/). This prevents the execution of
    arbitrary or unsafe code unlike `eval`.

    Args:
        expr: A string representing a mathematical expression, e.g. "2 + 3 * 4".

    Returns:
        The result of the evaluated expression.

    Raises:
        ValueError: If the expression contains unsupported syntax or node types.

    Example:
        >>> safe_eval_expression("2 + 3 * 4")
        14
    """
    # Handle edge cases
    if not expr or not expr.strip():
        raise ChartGenerationError("Expression cannot be empty")
    
    expr = expr.strip()
    
    # Simple number check - no need to parse if it's just a number
    try:
        return float(expr) if '.' in expr else int(expr)
    except ValueError:
        pass  # Continue with AST parsing
    
    operators = {
        Add: add,
        Sub: sub,
        Mult: mul,
        Div: truediv,
    }

    try:
        tree = parse(expr, mode='eval')
    except SyntaxError as e:
        raise ChartGenerationError(f"Invalid expression syntax: {expr}") from e

    def evaluate_node(node):
        if isinstance(node, Expression):
            return evaluate_node(node.body)
        elif isinstance(node, BinOp):
            left = evaluate_node(node.left)
            right = evaluate_node(node.right)
            
            # Check for division by zero
            if isinstance(node.op, Div) and right == 0:
                raise ChartGenerationError("Division by zero in expression")
            
            result = operators[type(node.op)](left, right)
            
            # Check for reasonable bounds (prevent overflow issues)
            if abs(result) > 1e10:
                raise ChartGenerationError(f"Result too large: {result}")
            
            return result
        elif isinstance(node, Num):
            return node.n
        # Handle newer Python versions that use Constant instead of Num
        elif hasattr(node, 'n'):  # Fallback for different Python versions
            return node.n
        elif hasattr(node, 'value') and isinstance(node.value, (int, float)):
            return node.value
        else:
            raise ChartGenerationError(f'Unsupported AST node type: {type(node)}')

    result = evaluate_node(tree.body)
    return result


def convert_dimensions(
        x: Union[float, str],
        y: Union[float, str],
        width: Union[float, str],
        height: Union[float, str],
        dimensions_format: str,
        slides_app: Optional[dict] = None
    ) -> Tuple[int, int, int, int]:
    """
    Converts position and size values to point-based (pt) dimensions for Slides API.

    Supports absolute (`pt`, `emu`) and relative units. Strings are safely
    evaluated as arithmetic expressions.

    Args:
        x: X-position of the object. Can be a number or an expression.
        y: Y-position of the object.
        width: Width of the object.
        height: Height of the object.
        dimensions_format: One of 'pt', 'emu', or 'relative'.
            - 'pt': Values are already in points.
            - 'emu': Converts EMUs to points.
            - 'relative': Interprets values as ratios of the page size.
        slides_app: Required if `dimensions_format` is 'relative'.
            Used to extract the actual page size for scaling.

    Returns:
        The converted (x, y, width, height) in points.

    Raises:
        ValueError: If `dimensions_format` is unsupported or if required
        data is missing for relative conversions.

    Example:
        >>> convert_dimensions("50 + 10", 20, "200", "100", "pt")
        (60, 20, 200, 100)
    """
    if isinstance(x, str):
        x = safe_eval_expression(x)
    if isinstance(y, str):
        y = safe_eval_expression(y)
    if isinstance(width, str):
        width = safe_eval_expression(width)
    if isinstance(height, str):
        height = safe_eval_expression(height)

    if dimensions_format in ('pt', 'emu', 'expression'):
        factor = 1 if dimensions_format in ('pt', 'expression') else 1 / 12700
        return tuple(int(val * factor) for val in (x, y, width, height))
    
    if dimensions_format == 'relative':
        if slides_app is None:
            raise ChartGenerationError('slides_app must be provided for relative dimensions conversion')
        
        def get_page_dimension(dim: str) -> float:
            dim_info = slides_app['pageSize'][dim]
            return dim_info['magnitude'] / 12700 if dim_info['unit'] == 'EMU' else dim_info['magnitude']
        
        page_width = get_page_dimension('width')
        page_height = get_page_dimension('height')
        
        return (
            int(x * page_width),
            int(y * page_height),
            int(width * page_width),
            int(height * page_height)
        )
    
    raise ChartGenerationError(f'Unsupported dimensions_format: {dimensions_format}')

def apply_alignment(
        x: int,
        y: int,
        width: int,
        height: int,
        alignment_format: str, 
        page_width_pt: int,
        page_height_pt: int
    ) -> Tuple[int, int]:
    """
    Applies alignment adjustments to chart or image position on a slide.

    Based on the specified alignment string (e.g., 'center-top'), it adjusts the
    X and Y coordinates relative to the slide dimensions.

    Args:
        x: Initial X-coordinate in points.
        y: Initial Y-coordinate in points.
        width: Width of the object in points.
        height: Height of the object in points.
        alignment_format: Alignment string in the format 'horizontal-vertical'.
            Supported horizontal values: 'left', 'center', 'right'.
            Supported vertical values: 'top', 'center', 'bottom'.
        page_width_pt: Width of the slide in points.
        page_height_pt: Height of the slide in points.

    Returns:
        The adjusted (x, y) coordinates in points.

    Raises:
        ValueError: If the alignment format is invalid.

    Example:
        >>> apply_alignment(0, 20, 300, 100, 'center-top', 720, 540)
        (210, 20)
    """
    try:
        horizontal_align, vertical_align = alignment_format.split('-')
    except ValueError:
        raise ChartGenerationError(f"Invalid alignment format: {alignment_format}. Expected format: 'horizontal-vertical'")
    
    # Horizontal alignment
    if horizontal_align == 'center':
        x = int((page_width_pt - width) / 2 + x)
    elif horizontal_align == 'right':
        x = page_width_pt - width - x
    elif horizontal_align != 'left':
        raise ChartGenerationError(f"Invalid horizontal alignment: {horizontal_align}. Supported: 'left', 'center', 'right'")

    # Vertical alignment
    if vertical_align == 'center':
        y = int((page_height_pt - height) / 2 + y)
    elif vertical_align == 'bottom':
        y = page_height_pt - height - y
    elif vertical_align != 'top':
        raise ChartGenerationError(f"Invalid vertical alignment: {vertical_align}. Supported: 'top', 'center', 'bottom'")

    return x, y

def compute_chart_dimensions(
        x: Union[float, str],
        y: Union[float, str], 
        width: Union[float, str],
        height: Union[float, str],
        dimensions_format: str = 'pt',
        alignment_format: Optional[str] = None,
        slides_app: Optional[dict] = None,
        page_width_pt: int = 720,
        page_height_pt: int = 540
    ) -> Tuple[int, int, int, int]:
    """
    Computes the final pixel dimensions and position for a chart.

    This method converts the chart's x, y, width, and height values into
    point units, accounting for the specified dimensions format and alignment.

    Args:
        x: X-position value
        y: Y-position value  
        width: Width value
        height: Height value
        dimensions_format: Format for dimension values ('pt', 'emu', 'relative')
        alignment_format: Optional alignment string (e.g., 'center-top')
        slides_app: Slide app metadata for relative positioning
        page_width_pt: Page width in points (for alignment)
        page_height_pt: Page height in points (for alignment)

    Returns:
        A tuple of (x, y, width, height) in points.
    """
    # Convert dimensions to points
    x_pt, y_pt, width_pt, height_pt = convert_dimensions(
        x, y, width, height, dimensions_format, slides_app
    )
    
    # Validate reasonable positioning bounds
    if width_pt <= 0 or height_pt <= 0:
        raise ChartGenerationError(f"Width and height must be positive, got: {width_pt}x{height_pt}")
    
    if width_pt > page_width_pt * 2 or height_pt > page_height_pt * 2:
        raise ChartGenerationError(f"Chart dimensions too large: {width_pt}x{height_pt} (page: {page_width_pt}x{page_height_pt})")
    
    # Apply alignment if specified
    if alignment_format:
        x_pt, y_pt = apply_alignment(
            x_pt, y_pt, width_pt, height_pt,
            alignment_format, page_width_pt, page_height_pt
        )
    
    # Ensure final coordinates are reasonable (allow negative for offsets)
    if abs(x_pt) > page_width_pt * 3 or abs(y_pt) > page_height_pt * 3:
        raise ChartGenerationError(f"Final position too far from slide: ({x_pt}, {y_pt})")
    
    return x_pt, y_pt, width_pt, height_pt
