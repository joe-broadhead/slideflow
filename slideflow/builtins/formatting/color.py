import decimal

def green_or_red(value):
    """
    Returns a color name based on whether the numeric value is positive or negative.

    Args:
        value: A number (int or float) to evaluate.

    Returns:
        str: 
            - 'green' if the value is greater than or equal to 0,
            - 'red' if the value is less than 0,
            - 'black' if the value is not a number.
    """
    if isinstance(value, decimal.Decimal):
        value = float(value)
        
    if isinstance(value, (int, float)):
        return "green" if value >= 0 else "red"
    return "black"

function_registry = {
    "green_or_red": green_or_red
}