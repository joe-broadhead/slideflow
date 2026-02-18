"""Registry path resolution helpers for CLI commands."""

from pathlib import Path
from typing import Iterable, List, Optional


def resolve_registry_paths(
    *,
    config_file: Path,
    cli_registry_paths: Optional[Iterable[Path]],
    config_registry: object,
) -> List[Path]:
    """Resolve registry file paths with config-relative precedence.

    Resolution order:
    1. Explicit CLI --registry values (kept as provided).
    2. `registry` values inside YAML config (resolved relative to config file).
    3. Defaults: `<config_dir>/registry.py`, then `./registry.py` if present.
    """
    if cli_registry_paths is not None:
        return list(cli_registry_paths)

    config_registry_paths = _parse_config_registry(config_registry, config_file.parent)
    if config_registry_paths:
        return config_registry_paths

    default_candidates = [
        (config_file.parent / "registry.py").resolve(),
        Path("registry.py").resolve(),
    ]
    resolved_defaults: List[Path] = []
    for candidate in default_candidates:
        if candidate.exists() and candidate not in resolved_defaults:
            resolved_defaults.append(candidate)
    return resolved_defaults


def _parse_config_registry(config_registry: object, config_dir: Path) -> List[Path]:
    if config_registry is None:
        return []

    if isinstance(config_registry, (str, Path)):
        return [_resolve_config_path(Path(config_registry), config_dir)]

    if isinstance(config_registry, list):
        return [
            _resolve_config_path(Path(entry), config_dir) for entry in config_registry
        ]

    raise ValueError("`registry` in config must be a path or list of paths")


def _resolve_config_path(path: Path, config_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()
