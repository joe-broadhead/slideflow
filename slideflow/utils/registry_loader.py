import importlib
from rich import print
from importlib.metadata import entry_points

def load_function_registry(module_path: str):
    """
    Loads a `function_registry` dictionary from the specified module.

    This function imports a module from the given module path and retrieves
    the top-level `function_registry` object, which must be a dictionary
    mapping string keys to callable functions.

    Example:
        load_function_registry("myproject.registry")

    Args:
        module_path: The dotted path to the Python module (e.g. "myproject.registry").

    Returns:
        dict: A dictionary of registered functions from the module.

    Raises:
        ImportError: If the module cannot be imported or does not contain a
            `function_registry` object.
        TypeError: If `function_registry` is not a dictionary.
    """
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_path}': {e}") from e

    if not hasattr(module, 'function_registry'):
        raise ImportError(f"Module '{module_path}' must define a 'function_registry' object.")

    registry = getattr(module, 'function_registry')
    if not isinstance(registry, dict):
        raise TypeError(f"'function_registry' in module '{module_path}' must be a dict.")

    return registry


def load_registry_from_entry_point(name: str = 'default'):
    """
    Loads a `function_registry` dictionary from a pyproject.toml entry point.

    This function retrieves a registered `function_registry` from an entry point
    defined under the `slideflow_registry` group in `pyproject.toml`.

    Compatible with both Python 3.9 and 3.10+.

    Example:
        load_registry_from_entry_point("default")

    Args:
        name: The name of the entry point to load. Defaults to "default".

    Returns:
        dict: A dictionary of registered functions loaded from the entry point.

    Raises:
        ValueError: If no matching entry point is found.
        TypeError: If the entry point does not return a dictionary.
        Exception: If an error occurs while loading the entry point.
    """
    try:
        # Python 3.10+
        try:
            eps = entry_points(group = 'slideflow_registry')
        except TypeError:
            # Python 3.9 fallback
            eps = entry_points().get('slideflow_registry', [])

        match = next((ep for ep in eps if ep.name == name), None)
        if not match:
            raise ValueError(
                f"No entry point '{name}' found in [project.entry-points.slideflow_registry]"
            )

        registry = match.load()
    except Exception as e:
        print(f"[red]❌ Failed to load entry point '{name}': {e}[/red]")
        raise

    if not isinstance(registry, dict):
        raise TypeError(
            f"Entry point '{name}' must return a dict, but got: {type(registry)}"
        )

    return registry
