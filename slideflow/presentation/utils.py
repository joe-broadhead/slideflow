from typing import Optional, Tuple, Union
from operator import add, sub, mul, truediv
from ast import Add, Sub, Mult, Div, parse, Expression, BinOp, Num

def safe_eval_expression(expr):
    """
    Safely evaluates a basic arithmetic expression using the AST module.

    Supports only basic binary operations: addition (+), subtraction (-),
    multiplication (*), and division (/). This prevents the execution of
    arbitrary or unsafe code unlike `eval`.

    Args:
        expr (str): A string representing a mathematical expression, e.g. "2 + 3 * 4".

    Returns:
        float | int: The result of the evaluated expression.

    Raises:
        ValueError: If the expression contains unsupported syntax or node types.

    Example:
        >>> safe_eval_expression("2 + 3 * 4")
        14
    """
    operators = {
        Add: add,
        Sub: sub,
        Mult: mul,
        Div: truediv,
    }

    tree = parse(expr, mode = 'eval')

    def evaluate_node(node):
        if isinstance(node, Expression):
            return evaluate_node(node.body)
        elif isinstance(node, BinOp):
            left = evaluate_node(node.left)
            right = evaluate_node(node.right)
            return operators[type(node.op)](left, right)
        elif isinstance(node, Num):
            return node.n
        else:
            raise ValueError(f'Unsupported AST node type: {type(node)}')

    return evaluate_node(tree.body)

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
        x (Union[float, str]): X-position of the object. Can be a number or an expression.
        y (Union[float, str]): Y-position of the object.
        width (Union[float, str]): Width of the object.
        height (Union[float, str]): Height of the object.
        dimensions_format (str): One of 'pt', 'emu', or 'relative'.
            - 'pt': Values are already in points.
            - 'emu': Converts EMUs to points.
            - 'relative': Interprets values as ratios of the page size.
        slides_app (Optional[dict]): Required if `dimensions_format` is 'relative'.
            Used to extract the actual page size for scaling.

    Returns:
        Tuple[int, int, int, int]: The converted (x, y, width, height) in points.

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

    if dimensions_format in ('pt', 'emu'):
        factor = 1 if dimensions_format == 'pt' else 1 / 12700
        return tuple(int(val * factor) for val in (x, y, width, height))
    
    if dimensions_format == 'relative':
        if slides_app is None:
            raise ValueError('slides_app must be provided for relative dimensions conversion')
        
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
    
    raise ValueError(f'Unsupported dimensions_format: {dimensions_format}')

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
        x (int): Initial X-coordinate in points.
        y (int): Initial Y-coordinate in points.
        width (int): Width of the object in points.
        height (int): Height of the object in points.
        alignment_format (str): Alignment string in the format 'horizontal-vertical'.
            Supported horizontal values: 'left', 'center', 'right'.
            Supported vertical values: 'top', 'center', 'bottom'.
        page_width_pt (int): Width of the slide in points.
        page_height_pt (int): Height of the slide in points.

    Returns:
        Tuple[int, int]: The adjusted (x, y) coordinates in points.

    Raises:
        ValueError: If the alignment format is invalid.

    Example:
        >>> apply_alignment(0, 20, 300, 100, 'center-top', 720, 540)
        (210, 20)
    """
    horizontal_align, vertical_align = alignment_format.split('-')
    
    if horizontal_align == 'center':
        x = int((page_width_pt - width) / 2 + x)
    elif horizontal_align == 'right':
        x = page_width_pt - width - x

    if vertical_align == 'center':
        y = int((page_height_pt - height) / 2 + y)
    elif vertical_align == 'bottom':
        y = page_height_pt - height - y

    return x, y
