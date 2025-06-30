import re
import sys
import yaml
import pkgutil
import importlib.util
from pathlib import Path
from functools import cached_property
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, List, Mapping, Callable, Sequence

from slideflow.utilities.exceptions import ConfigurationError

def render_params(obj: Any, params: Mapping[str, str]) -> Any:
    if isinstance(obj, Mapping):
        return {k: render_params(v, params) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        return [render_params(v, params) for v in obj]
    if isinstance(obj, str):
        _DOUBLE_BRACE_RE = re.compile(r"{{.*?}}")
        if _DOUBLE_BRACE_RE.search(obj):
            return obj
        try:
            return obj.format(**params)
        except KeyError:
            return obj
    return obj

def load_registry_from_path(registry_path: Path) -> dict[str, Callable]:
    path = registry_path.resolve()
    if not path.exists():
        raise ConfigurationError(f"Registry file not found: {path}")

    module_name = path.stem
    package = path.parent.name
    full_name = f"{package}.{module_name}"
    sys.path.insert(0, str(path.parent.parent))

    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = package
    spec.loader.exec_module(module)  # type: ignore

    registry = getattr(module, "function_registry", None)
    if not isinstance(registry, dict):
        raise ConfigurationError(f"`function_registry` must be a dict in {path}")
    return registry

def resolve_functions(obj: Any, registry: dict[str, Callable]) -> Any:
    if isinstance(obj, Mapping):
        return {k: resolve_functions(v, registry) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        return [resolve_functions(v, registry) for v in obj]
    if isinstance(obj, str) and obj in registry:
        return registry[obj]
    return obj

def search_registries_in_package() -> dict[str, Callable]:
    """
    Walks the top‐level package (in which this module lives), imports every submodule,
    and picks up any `function_registry: dict[str, Callable]` it finds.
    """
    merged: dict[str, Callable] = {}
    # determine your root package name
    pkg_name = __package__.split(".")[0] if __package__ else None
    if not pkg_name:
        return merged

    pkg = importlib.import_module(pkg_name)
    for finder, mod_name, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        reg = getattr(mod, "function_registry", None)
        if isinstance(reg, dict):
            merged.update(reg)
    return merged

class ConfigLoader(BaseModel):
    """
    yaml_path      : Path to a YAML file
    registry_paths : List of .py files exporting `function_registry: dict[str, Callable]`
    params         : mapping for {param} templates
    """
    yaml_path: Path = Field(..., description = "YAML file to load")
    registry_paths: List[Path] = Field(
        ..., description = "One or more Python files defining `function_registry`"
    )
    params: Mapping[str, str] = Field(
        default_factory = dict,
        description = "Values for {param} substitution"
    )

    model_config = ConfigDict(
        arbitrary_types_allowed = True
    )

    @cached_property
    def config(self) -> Any:
        raw = yaml.safe_load(self.yaml_path.read_text(encoding = "utf-8"))
        rendered = render_params(raw, self.params)

        merged_registry = search_registries_in_package()
        for path in self.registry_paths:
            reg = load_registry_from_path(path)
            merged_registry.update(reg)
        return resolve_functions(rendered, merged_registry)
