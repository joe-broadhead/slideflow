import importlib.util
from pathlib import Path

def load_function_registry(registry_path: str):
    """
    Load a function registry directly from a Python file.
    
    Args:
        registry_path (str): Path to a Python file containing 'function_registry'.

    Returns:
        dict: Loaded function registry.
    """
    path = Path(registry_path)
    if not path.exists():
        raise FileNotFoundError(f"Registry file not found: {path}")

    spec = importlib.util.spec_from_file_location("user_registry", path)
    user_registry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(user_registry)

    if not hasattr(user_registry, 'function_registry'):
        raise AttributeError(f"'function_registry' not found in {registry_path}")

    registry = getattr(user_registry, 'function_registry')

    if not isinstance(registry, dict):
        raise TypeError(f"'function_registry' must be a dict, but got {type(registry)}")

    return registry
