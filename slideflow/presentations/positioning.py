"""Chart positioning and dimension calculation utilities for presentations.

This module provides safe mathematical expression evaluation and coordinate
transformation functions for positioning charts and elements within presentation
slides. It handles multiple coordinate systems, alignment calculations, and
dimension conversions while maintaining security through safe expression parsing.

Key Features:
    - Safe arithmetic expression evaluation using AST parsing
    - Multiple coordinate system support (points, EMUs, relative)
    - Flexible alignment system (horizontal-vertical combinations)
    - Dimension validation and bounds checking
    - Cross-platform coordinate system conversion

Coordinate Systems:
    - Points (pt): Standard presentation unit (1/72 inch)
    - EMUs: English Metric Units used by Office formats (1/12700 point)
    - Relative: Proportional to slide dimensions (0.0-1.0)
    - Expression: String expressions evaluated safely to numeric values

Example:
    Basic chart positioning with expression evaluation:
    
    >>> from slideflow.presentations.positioning import compute_chart_dimensions
    >>> 
    >>> # Position chart with calculated dimensions
    >>> x, y, w, h = compute_chart_dimensions(
    ...     x="50 + 25",           # Expression: results in 75pt
    ...     y=100,                 # Direct value: 100pt
    ...     width="400",           # String number: 400pt
    ...     height="300",          # String number: 300pt
    ...     dimensions_format="pt",
    ...     alignment_format="center-top",
    ...     page_width_pt=720,
    ...     page_height_pt=540
    ... )
    >>> print(f"Final position: ({x}, {y}) size: {w}x{h}")
    
    Relative positioning for responsive layouts:
    
    >>> x, y, w, h = compute_chart_dimensions(
    ...     x=0.1,                 # 10% from left edge
    ...     y=0.2,                 # 20% from top edge
    ...     width=0.6,             # 60% of slide width
    ...     height=0.4,            # 40% of slide height
    ...     dimensions_format="relative",
    ...     slides_app={"pageSize": {"width": {...}, "height": {...}}}
    ... )

Security:
    All string expressions are parsed using Python's AST module to prevent
    code execution attacks. Only basic arithmetic operations are supported.
"""

from typing import Optional, Tuple, Union
from operator import add, sub, mul, truediv
from ast import Add, Sub, Mult, Div, parse, Expression, BinOp, Num

from slideflow.utilities.exceptions import ChartGenerationError

def safe_eval_expression(expr: str) -> Union[float, int]:
    """Safely evaluate arithmetic expressions without code execution risks.
    
    This function provides secure evaluation of mathematical expressions by
    parsing them with Python's AST module and only allowing basic arithmetic
    operations. It prevents arbitrary code execution that would be possible
    with eval() while supporting common mathematical expressions.
    
    Supported Operations:
        - Addition: a + b
        - Subtraction: a - b
        - Multiplication: a * b
        - Division: a / b (with zero-division protection)
        
    Security Features:
        - No function calls or variable access
        - No string operations or imports
        - No loops or conditional statements
        - Bounds checking to prevent overflow
        - Division by zero protection
    
    Args:
        expr: Mathematical expression string to evaluate. Can contain numbers,
            parentheses, and the four basic arithmetic operators. Whitespace
            is ignored.
            
    Returns:
        Numeric result of the expression. Returns int if the result has no
        decimal component, float otherwise.
        
    Raises:
        ChartGenerationError: If the expression is empty, contains invalid
            syntax, uses unsupported operations, results in division by zero,
            or produces results outside reasonable bounds.
            
    Example:
        Basic arithmetic expressions:
        
        >>> safe_eval_expression("10 + 5")
        15
        >>> safe_eval_expression("100 - 25")
        75
        >>> safe_eval_expression("20 * 3")
        60
        >>> safe_eval_expression("400 / 2")
        200.0
        
        Complex expressions with parentheses:
        
        >>> safe_eval_expression("(100 + 50) * 2")
        300
        >>> safe_eval_expression("200 + 100 / 4")
        225.0
        
        Chart positioning examples:
        
        >>> width = safe_eval_expression("400 + 100")  # 500pt chart width
        >>> x_offset = safe_eval_expression("50 * 2")   # 100pt from left
        >>> padding = safe_eval_expression("20 + 10")   # 30pt padding
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
    """Convert position and dimension values to standardized point units.
    
    This function handles coordinate system conversion for chart positioning,
    supporting multiple input formats and automatically evaluating string
    expressions. It normalizes all coordinates to points (pt), which is the
    standard unit used by presentation APIs.
    
    Supported Formats:
        - 'pt' or 'expression': Values in points (1/72 inch), expressions evaluated
        - 'emu': English Metric Units (1/12700 point), converted to points
        - 'relative': Values as ratios (0.0-1.0) of slide dimensions
    
    The function safely evaluates string expressions in any coordinate system,
    allowing for calculated positioning like "margin + offset" or "width / 2".
    
    Args:
        x: Horizontal position value. Can be numeric or string expression.
        y: Vertical position value. Can be numeric or string expression.
        width: Object width value. Can be numeric or string expression.
        height: Object height value. Can be numeric or string expression.
        dimensions_format: Coordinate system identifier ('pt', 'emu', 'relative').
        slides_app: Presentation metadata containing page dimensions. Required
            only when dimensions_format is 'relative'.
            
    Returns:
        Tuple of (x, y, width, height) converted to integer point values.
        
    Raises:
        ChartGenerationError: If dimensions_format is unsupported, slides_app
            is missing for relative coordinates, or expressions are invalid.
            
    Example:
        Point-based positioning with expressions:
        
        >>> convert_dimensions(
        ...     x="50 + 25",      # 75pt from left
        ...     y="100",          # 100pt from top
        ...     width="400",      # 400pt wide
        ...     height="300",     # 300pt tall
        ...     dimensions_format="pt"
        ... )
        (75, 100, 400, 300)
        
        EMU to points conversion:
        
        >>> convert_dimensions(
        ...     x=635000,         # ~50pt in EMUs
        ...     y=1270000,        # ~100pt in EMUs
        ...     width=5080000,    # ~400pt in EMUs
        ...     height=3810000,   # ~300pt in EMUs
        ...     dimensions_format="emu"
        ... )
        (50, 100, 400, 300)
        
        Relative positioning (responsive layout):
        
        >>> slides_app = {
        ...     "pageSize": {
        ...         "width": {"magnitude": 9144000, "unit": "EMU"},   # 720pt
        ...         "height": {"magnitude": 6858000, "unit": "EMU"}   # 540pt
        ...     }
        ... }
        >>> convert_dimensions(
        ...     x=0.1,            # 10% from left = 72pt
        ...     y=0.2,            # 20% from top = 108pt
        ...     width=0.5,        # 50% of width = 360pt
        ...     height=0.4,       # 40% of height = 216pt
        ...     dimensions_format="relative",
        ...     slides_app=slides_app
        ... )
        (72, 108, 360, 216)
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
    """Apply alignment transformations to object coordinates on a slide.
    
    This function adjusts the position coordinates of charts, images, or other
    objects based on alignment specifications. It supports standard alignment
    patterns used in presentation software, allowing objects to be positioned
    relative to slide boundaries rather than absolute coordinates.
    
    The alignment system uses a 'horizontal-vertical' format where the horizontal
    component affects X positioning and the vertical component affects Y positioning.
    The initial x,y coordinates are treated as offsets from the alignment anchor.
    
    Alignment Behavior:
        - 'left': X coordinate used as-is (offset from left edge)
        - 'center': Object centered horizontally, X used as additional offset
        - 'right': Object aligned to right edge, X used as offset from right
        - 'top': Y coordinate used as-is (offset from top edge)
        - 'center': Object centered vertically, Y used as additional offset
        - 'bottom': Object aligned to bottom edge, Y used as offset from bottom
    
    Args:
        x: Initial horizontal coordinate in points, interpreted as offset from
            the alignment anchor position.
        y: Initial vertical coordinate in points, interpreted as offset from
            the alignment anchor position.
        width: Object width in points, used for center and right alignment calculations.
        height: Object height in points, used for center and bottom alignment calculations.
        alignment_format: Alignment specification in 'horizontal-vertical' format.
            Valid combinations: 'left-top', 'center-center', 'right-bottom', etc.
        page_width_pt: Slide width in points for horizontal alignment calculations.
        page_height_pt: Slide height in points for vertical alignment calculations.
        
    Returns:
        Tuple of adjusted (x, y) coordinates in points, ready for use in
        presentation APIs.
        
    Raises:
        ChartGenerationError: If alignment_format doesn't follow expected pattern
            or contains unsupported alignment values.
            
    Example:
        Center alignment with offset:
        
        >>> apply_alignment(
        ...     x=10,              # 10pt offset from center
        ...     y=20,              # 20pt offset from top
        ...     width=300,         # Object is 300pt wide
        ...     height=100,        # Object is 100pt tall
        ...     alignment_format="center-top",
        ...     page_width_pt=720, # Standard slide width
        ...     page_height_pt=540 # Standard slide height
        ... )
        (220, 20)  # Centered horizontally (720-300)/2 + 10, top-aligned + 20
        
        Right-bottom alignment:
        
        >>> apply_alignment(
        ...     x=50,              # 50pt margin from right edge
        ...     y=30,              # 30pt margin from bottom edge
        ...     width=200,
        ...     height=150,
        ...     alignment_format="right-bottom",
        ...     page_width_pt=720,
        ...     page_height_pt=540
        ... )
        (470, 360)  # 720-200-50=470, 540-150-30=360
        
        Complete center alignment:
        
        >>> apply_alignment(
        ...     x=0, y=0,          # No offset from center
        ...     width=400, height=300,
        ...     alignment_format="center-center",
        ...     page_width_pt=720,
        ...     page_height_pt=540
        ... )
        (160, 120)  # Perfect center: (720-400)/2, (540-300)/2
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
    """Compute final chart dimensions and position with full validation.
    
    This is the main entry point for chart positioning calculations. It combines
    coordinate conversion, alignment processing, and validation to produce final
    positioning values ready for presentation APIs. The function handles all
    supported coordinate systems and provides comprehensive error checking.
    
    Processing Pipeline:
        1. Convert coordinates from input format to points
        2. Validate dimensions are positive and reasonable
        3. Apply alignment transformations if specified
        4. Perform final bounds checking
        5. Return validated coordinates
    
    The function uses standard presentation dimensions (720x540pt) as defaults,
    which correspond to typical slide aspect ratios, but can be customized for
    different presentation formats.
    
    Args:
        x: Horizontal position specification. Can be numeric value or string
            expression to be evaluated.
        y: Vertical position specification. Can be numeric value or string
            expression to be evaluated.
        width: Object width specification. Can be numeric value or string
            expression to be evaluated.
        height: Object height specification. Can be numeric value or string
            expression to be evaluated.
        dimensions_format: Coordinate system for input values. Supports 'pt'
            (points), 'emu' (English Metric Units), 'relative' (proportional),
            and 'expression' (treated as points with expression evaluation).
        alignment_format: Optional alignment specification in 'horizontal-vertical'
            format. If provided, coordinates are adjusted relative to slide edges.
        slides_app: Presentation metadata required for relative coordinate
            conversion. Must contain pageSize information.
        page_width_pt: Slide width in points for alignment calculations and
            validation. Defaults to 720pt (standard widescreen).
        page_height_pt: Slide height in points for alignment calculations and
            validation. Defaults to 540pt (standard widescreen).
            
    Returns:
        Tuple of (x, y, width, height) in integer point values, validated and
        ready for use in presentation APIs.
        
    Raises:
        ChartGenerationError: If dimensions are invalid (negative, zero, or
            excessively large), coordinates are out of reasonable bounds,
            expressions cannot be evaluated, or required parameters are missing.
            
    Example:
        Basic chart positioning:
        
        >>> x, y, w, h = compute_chart_dimensions(
        ...     x=100,
        ...     y=150,
        ...     width=400,
        ...     height=300
        ... )
        >>> # Result: (100, 150, 400, 300)
        
        Expression-based positioning:
        
        >>> x, y, w, h = compute_chart_dimensions(
        ...     x="50 + 25",           # Calculated: 75
        ...     y="100 * 1.5",         # Calculated: 150
        ...     width="400",           # String number: 400
        ...     height="200 + 100",    # Calculated: 300
        ...     dimensions_format="pt"
        ... )
        >>> # Result: (75, 150, 400, 300)
        
        Centered chart with alignment:
        
        >>> x, y, w, h = compute_chart_dimensions(
        ...     x=0,                   # No offset from center
        ...     y=50,                  # 50pt offset from top
        ...     width=500,
        ...     height=300,
        ...     alignment_format="center-top",
        ...     page_width_pt=720,
        ...     page_height_pt=540
        ... )
        >>> # Result: (110, 50, 500, 300) - centered horizontally
        
        Relative positioning for responsive layouts:
        
        >>> slides_app = {
        ...     "pageSize": {
        ...         "width": {"magnitude": 9144000, "unit": "EMU"},
        ...         "height": {"magnitude": 6858000, "unit": "EMU"}
        ...     }
        ... }
        >>> x, y, w, h = compute_chart_dimensions(
        ...     x=0.1,                # 10% from left
        ...     y=0.2,                # 20% from top
        ...     width=0.6,            # 60% of slide width
        ...     height=0.4,           # 40% of slide height
        ...     dimensions_format="relative",
        ...     slides_app=slides_app
        ... )
        >>> # Result: (72, 108, 432, 216) - responsive positioning
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
