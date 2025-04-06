import sys
import importlib.util
from pathlib import Path

def load_function_registry(registry_path: str) -> dict:
    """
    Loads a function registry dictionary from a Python file path.

    This function dynamically imports a Python module from the given file path,
    sets up the module to support relative imports, and extracts a top-level
    variable called `function_registry`. The registry is expected to be a 
    dictionary mapping function names to callables.

    Useful when the registry file includes relative imports (e.g. `from .charts import ...`).

    Args:
        registry_path (str): Path to the Python file containing a `function_registry` dict.

    Returns:
        dict: A dictionary of named functions imported from the module.

    Raises:
        FileNotFoundError: If the file does not exist at the given path.
        AttributeError: If the module does not define a `function_registry` variable.
        TypeError: If `function_registry` is not a dictionary.
    """
    path = Path(registry_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f'Registry file not found: {path}')

    # Infer a fake package name based on its folder
    module_name = path.stem
    package_name = path.parent.name
    full_name = f"{package_name}.{module_name}"

    # Add its parent folder to sys.path
    sys.path.insert(0, str(path.parent.parent))

    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)

    # This makes relative imports work
    module.__package__ = package_name

    spec.loader.exec_module(module)

    if not hasattr(module, 'function_registry'):
        raise AttributeError(f"'function_registry' not found in {registry_path}")

    registry = getattr(module, 'function_registry')

    if not isinstance(registry, dict):
        raise TypeError(f"'function_registry' must be a dict, but got {type(registry)}")

    return registry
