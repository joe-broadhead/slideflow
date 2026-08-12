"""DBT (Data Build Tool) connector for Slideflow with Databricks integration.

This module provides connectors and configurations for executing DBT models
and using their compiled SQL queries as data sources. It integrates DBT's
transformation logic with Databricks execution, enabling presentations to
use sophisticated data transformations.

The DBT connector system includes:
    - Git repository cloning and branch management
    - DBT project compilation and dependency management
    - Manifest parsing to extract compiled SQL queries
    - Integration with Databricks for query execution
    - Comprehensive caching of compiled projects
    - Performance monitoring and logging

Key Features:
    - Automatic DBT project cloning from Git repositories
    - Model compilation with custom variables and targets
    - Thread-safe caching of compiled projects
    - Integration with Databricks SQL warehouses
    - Performance tracking for compilation and execution
    - Error handling and comprehensive logging

Authentication:
    Uses the same Databricks authentication as DatabricksConnector:
    - DATABRICKS_HOST: Databricks workspace hostname
    - DATABRICKS_HTTP_PATH: SQL warehouse HTTP path
    - DATABRICKS_ACCESS_TOKEN: Authentication token

Example:
    Using DBT models in presentations:

    >>> from slideflow.data.connectors.dbt import DBTDatabricksSourceConfig
    >>>
    >>> # Create configuration for a DBT model
    >>> config = DBTDatabricksSourceConfig(
    ...     name="monthly_metrics",
    ...     type="databricks_dbt",
    ...     model_alias="monthly_revenue_summary",
    ...     package_url="https://github.com/company/dbt-project.git",
    ...     project_dir="/tmp/dbt_project",
    ...     branch="main",
    ...     target="prod"
    ... )
    >>>
    >>> # Fetch data using compiled DBT SQL
    >>> data = config.fetch_data()
    >>> print(f"Retrieved {len(data)} rows from DBT model")
"""

import hashlib
import json
import os
import re
import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterator, Literal, Optional, Sequence, Type

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from slideflow.citations import (
    CitationEntry,
    build_repo_file_url,
    canonical_repo_web_url,
    fingerprint_text,
)
from slideflow.constants import Defaults
from slideflow.data.connectors.base import BaseSourceConfig, DataConnector, SQLExecutor
from slideflow.data.connectors.bigquery import BigQuerySQLExecutor
from slideflow.data.connectors.duckdb import DuckDBSQLExecutor
from slideflow.data.connectors.redshift import RedshiftSQLExecutor
from slideflow.utilities.exceptions import DataSourceError
from slideflow.utilities.logging import get_logger, log_data_operation, log_performance

logger = get_logger(__name__)

_dbt_runner_cls: Any = None
try:
    from dbt.cli.main import dbtRunner as _imported_dbt_runner_cls

    _dbt_runner_cls = _imported_dbt_runner_cls
except ImportError:  # pragma: no cover - exercised in optional-dependency tests
    pass

_git_repo_cls: Any = None
try:
    from git import Repo as _imported_git_repo_cls

    _git_repo_cls = _imported_git_repo_cls
except ImportError:  # pragma: no cover - exercised in optional-dependency tests
    pass

# Keep module-level symbols for test monkeypatch compatibility.
dbtRunner = _dbt_runner_cls
Repo = _git_repo_cls

# Global cache for compiled DBT projects
_prepared_workspaces_cache: dict[tuple, Path] = {}
_prepared_workspaces_last_access: dict[tuple, float] = {}
_workspace_preparation_inflight: dict[tuple, threading.Event] = {}
_prepared_workspaces_in_use: dict[Path, int] = {}
_pending_workspace_cleanup_dirs: set[Path] = set()
_dbt_invocation_lock = threading.Lock()
_compiled_projects_cache: dict[tuple, Path] = {}
_compiled_projects_last_access: dict[tuple, float] = {}
_compilation_inflight: dict[tuple, threading.Event] = {}
_compilation_failures: dict[tuple, tuple[float, str]] = {}
_compiled_projects_in_use: dict[Path, int] = {}
_pending_cleanup_dirs: set[Path] = set()
_manifest_index_cache: dict[Path, "_ManifestIndex"] = {}
_manifest_index_inflight: dict[Path, threading.Event] = {}
_compiled_project_coverage: dict[tuple, frozenset[str]] = {}
_selection_locks: dict[tuple, threading.Lock] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class _ManifestNodeIndexEntry:
    """Indexed DBT manifest node metadata used for model resolution."""

    unique_id: str
    alias: str
    package_name: Optional[str]
    model_name: Optional[str]
    compiled_path: Optional[str]
    original_file_path: Optional[str] = None


@dataclass(frozen=True)
class _ManifestIndex:
    """Fast lookup index for a compiled DBT manifest."""

    by_alias: dict[str, list[_ManifestNodeIndexEntry]]
    by_unique_id: dict[str, _ManifestNodeIndexEntry]


@dataclass(frozen=True)
class DBTCompiledModelInfo:
    """Compiled dbt model metadata and SQL payload."""

    sql_text: str
    unique_id: str
    alias: str
    package_name: Optional[str]
    model_name: Optional[str]
    compiled_path: Optional[str]
    model_path: Optional[str]
    repo_url: Optional[str]
    file_url: Optional[str]
    ref: Optional[str]


def _manifest_cache_key(clone_dir: Path) -> Path:
    """Normalize clone_dir for manifest index cache lookups."""
    return clone_dir.resolve()


def _require_dbt_runner_class() -> Any:
    """Return dbtRunner class or raise actionable install guidance."""
    if dbtRunner is None:
        raise DataSourceError(
            "dbt-core is required for dbt sources. "
            "Install with: pip install slideflow-presentations[dbt]"
        )
    return dbtRunner


def _require_repo_class() -> Any:
    """Return GitPython Repo class or raise actionable install guidance."""
    if Repo is None:
        raise DataSourceError(
            "gitpython is required for dbt sources that clone repositories. "
            "Install with: pip install slideflow-presentations[dbt]"
        )
    return Repo


def _create_databricks_sql_executor() -> SQLExecutor:
    """Create Databricks SQL executor lazily to keep base installs lightweight."""
    try:
        from slideflow.data.connectors.databricks import DatabricksSQLExecutor
    except ImportError as error:
        raise DataSourceError(
            "databricks-sql-connector is required for dbt warehouse.type=databricks "
            "or databricks_dbt sources. Install with: "
            "pip install slideflow-presentations[dbt]"
        ) from error
    return DatabricksSQLExecutor()


def _drop_manifest_index_locked(clone_dir: Path) -> None:
    """Remove manifest cache entries for a clone dir. Requires caller lock."""
    key = _manifest_cache_key(clone_dir)
    _manifest_index_cache.pop(key, None)
    pending = _manifest_index_inflight.pop(key, None)
    if pending is not None:
        pending.set()


def _drop_manifest_indexes_under_locked(project_dir: Path) -> None:
    """Remove manifest indexes rooted in a managed project directory."""
    project_dir = project_dir.resolve()
    cached_keys = [
        key for key in _manifest_index_cache if _is_path_within(key, project_dir)
    ]
    inflight_keys = [
        key for key in _manifest_index_inflight if _is_path_within(key, project_dir)
    ]
    for key in cached_keys:
        _manifest_index_cache.pop(key, None)
    for key in inflight_keys:
        pending = _manifest_index_inflight.pop(key, None)
        if pending is not None:
            pending.set()


def _drop_manifest_index(clone_dir: Path) -> None:
    """Remove manifest cache entries for a clone dir."""
    with _cache_lock:
        _drop_manifest_index_locked(clone_dir)


def _load_manifest_index(clone_dir: Path) -> _ManifestIndex:
    """Parse manifest.json and build lookup indexes for models/analyses."""
    manifest_path = clone_dir / "target" / "manifest.json"
    if not manifest_path.exists():
        raise DataSourceError(f"manifest.json not found at {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    by_alias: dict[str, list[_ManifestNodeIndexEntry]] = {}
    by_unique_id: dict[str, _ManifestNodeIndexEntry] = {}

    for unique_id, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") not in ("model", "analysis"):
            continue

        alias = node.get("alias")
        if not alias:
            continue

        compiled_path = node.get("compiled_path")
        entry = _ManifestNodeIndexEntry(
            unique_id=str(unique_id),
            alias=str(alias),
            package_name=node.get("package_name"),
            model_name=node.get("name"),
            compiled_path=str(compiled_path) if compiled_path else None,
            original_file_path=(
                str(node.get("original_file_path"))
                if node.get("original_file_path")
                else None
            ),
        )

        by_alias.setdefault(entry.alias, []).append(entry)
        by_unique_id[entry.unique_id] = entry

    return _ManifestIndex(by_alias=by_alias, by_unique_id=by_unique_id)


def _get_manifest_index(clone_dir: Path) -> _ManifestIndex:
    """Get or build a manifest index for a compiled clone directory."""
    key = _manifest_cache_key(clone_dir)

    while True:
        with _cache_lock:
            cached = _manifest_index_cache.get(key)
            if cached is not None:
                return cached

            pending = _manifest_index_inflight.get(key)
            if pending is None:
                pending = threading.Event()
                _manifest_index_inflight[key] = pending
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            pending.wait()
            continue

        try:
            index = _load_manifest_index(key)
        except BaseException:
            with _cache_lock:
                event = _manifest_index_inflight.pop(key, None)
                if event is not None:
                    event.set()
            raise

        with _cache_lock:
            _manifest_index_cache[key] = index
            event = _manifest_index_inflight.pop(key, None)
            if event is not None:
                event.set()

        return index


def _format_manifest_candidate(entry: _ManifestNodeIndexEntry) -> str:
    """Render an indexed manifest candidate for error diagnostics."""
    package_name = entry.package_name or "unknown-package"
    model_name = entry.model_name or "unknown-model"
    return (
        f"{entry.unique_id} (alias={entry.alias}, package_name={package_name}, "
        f"model_name={model_name})"
    )


def _format_selector_context(
    model_unique_id: Optional[str],
    model_package_name: Optional[str],
    model_name: Optional[str],
) -> str:
    """Format optional selector fields for user-facing error messages."""
    selectors = []
    if model_unique_id:
        selectors.append(f"model_unique_id='{model_unique_id}'")
    if model_package_name:
        selectors.append(f"model_package_name='{model_package_name}'")
    if model_name:
        selectors.append(f"model_name='{model_name}'")
    if not selectors:
        return ""
    return " with selectors " + ", ".join(selectors)


def _sanitize_git_url(git_url: str) -> str:
    """Redact embedded basic-auth credentials from Git URLs."""
    return re.sub(r"(https?://)([^/@]+)@", r"\1***@", git_url)


def _resolve_repo_ref(clone_dir: Path, branch: Optional[str]) -> Optional[str]:
    """Return immutable commit SHA when available, otherwise branch/default."""
    try:
        repo_cls = _require_repo_class()
        repo = repo_cls(clone_dir)
        return repo.head.commit.hexsha
    except Exception:
        return branch or "default"


def _clone_repo(git_url: str, clone_dir: Path, branch: Optional[str]) -> None:
    """Clone a Git repository for DBT project access.

    Clones the specified Git repository to a local directory, optionally
    checking out a specific branch. Removes any existing directory at the
    target location before cloning.

    It supports expanding an environment variable for authentication tokens
    in the format: https://$TOKEN_NAME@...

    Args:
        git_url: Git repository URL to clone.
        clone_dir: Local directory path where the repository will be cloned.
        branch: Optional branch name to checkout. If None, uses default branch.

    Raises:
        DataSourceError: If the Git operation fails or the token variable is not set.

    Example:
        >>> _clone_repo(
        ...     "https://github.com/company/dbt-project.git",
        ...     Path("/tmp/dbt_project"),
        ...     "main"
        ... )
    """
    start_time = time.time()
    repo_cls = _require_repo_class()

    # Expand environment variable for token
    match = re.search(r"\$([A-Z_]+)", git_url)
    if match:
        token_name = match.group(1)
        token = os.getenv(token_name)
        if not token:
            raise DataSourceError(
                f"Environment variable {token_name} not set for Git authentication."
            )
        git_url = git_url.replace(f"${token_name}", token)
    safe_git_url = _sanitize_git_url(git_url)

    if clone_dir.exists():
        _drop_manifest_index(clone_dir)
        managed_root = clone_dir.parent
        if managed_root.name != ".slideflow_dbt_clones" or not _is_path_within(
            clone_dir, managed_root
        ):
            raise DataSourceError(
                "Refusing to delete unmanaged DBT clone directory. "
                f"clone_dir={clone_dir}"
            )
        shutil.rmtree(clone_dir)
    try:
        if branch:
            repo_cls.clone_from(git_url, clone_dir, branch=branch)
        else:
            repo_cls.clone_from(git_url, clone_dir)
        duration = time.time() - start_time
        log_data_operation(
            "clone",
            "dbt_project",
            context={
                "git_url": safe_git_url,
                "branch": branch or "default",
                "target_dir": str(clone_dir),
                "duration_seconds": duration,
            },
        )
    except Exception as e:
        duration = time.time() - start_time
        safe_error = _sanitize_git_url(str(e))
        log_data_operation(
            "clone",
            "dbt_project",
            context={
                "git_url": safe_git_url,
                "error": safe_error,
                "duration_seconds": duration,
            },
        )
        raise DataSourceError(f"Error cloning {safe_git_url}: {safe_error}")


def _is_path_within(path: Path, parent: Path) -> bool:
    """Return True when path is inside parent (or equal to parent)."""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _canonical_profiles_dir(profiles_dir: Optional[str]) -> Optional[str]:
    """Normalize profiles_dir to an absolute path string when present."""
    if not profiles_dir:
        return None
    return str(Path(profiles_dir).resolve())


def _canonical_project_dir(project_dir: str) -> str:
    """Normalize project_dir to an absolute path string."""
    return str(Path(project_dir).expanduser().resolve())


def _resolve_dbt_cache_max_entries() -> int:
    """Resolve max DBT compiled cache entries from env/defaults."""
    raw_value = os.getenv("SLIDEFLOW_DBT_CACHE_MAX_ENTRIES")
    if raw_value is None:
        return Defaults.DBT_CACHE_MAX_ENTRIES
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid SLIDEFLOW_DBT_CACHE_MAX_ENTRIES value '%s'; using default %s",
            raw_value,
            Defaults.DBT_CACHE_MAX_ENTRIES,
        )
        return Defaults.DBT_CACHE_MAX_ENTRIES
    return max(parsed, 1)


def _resolve_dbt_compile_failure_backoff_seconds() -> float:
    """Resolve compile failure backoff window (seconds) from env/defaults."""
    raw_value = os.getenv("SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S")
    if raw_value is None:
        return float(Defaults.DBT_COMPILE_FAILURE_BACKOFF_S)
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid SLIDEFLOW_DBT_COMPILE_FAILURE_BACKOFF_S value '%s'; using default %s",
            raw_value,
            Defaults.DBT_COMPILE_FAILURE_BACKOFF_S,
        )
        return float(Defaults.DBT_COMPILE_FAILURE_BACKOFF_S)
    return max(parsed, 0.0)


def _resolve_dbt_failure_cache_max_entries() -> int:
    """Resolve max entries for compile failure cache from env/defaults."""
    raw_value = os.getenv("SLIDEFLOW_DBT_FAILURE_CACHE_MAX_ENTRIES")
    if raw_value is None:
        return Defaults.DBT_FAILURE_CACHE_MAX_ENTRIES
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid SLIDEFLOW_DBT_FAILURE_CACHE_MAX_ENTRIES value '%s'; using default %s",
            raw_value,
            Defaults.DBT_FAILURE_CACHE_MAX_ENTRIES,
        )
        return Defaults.DBT_FAILURE_CACHE_MAX_ENTRIES
    return max(parsed, 1)


def _cleanup_managed_clone_dir(clone_dir: Path) -> None:
    """Best-effort removal of managed clone directories during cache eviction."""
    with _cache_lock:
        _drop_manifest_indexes_under_locked(clone_dir)
    managed_root = clone_dir.parent
    if managed_root.name != ".slideflow_dbt_clones" or not _is_path_within(
        clone_dir, managed_root
    ):
        logger.warning(
            "Refusing to delete unmanaged DBT clone directory: %s", clone_dir
        )
        return

    if not clone_dir.exists():
        return

    try:
        shutil.rmtree(clone_dir)
        workspace_log_dir = (
            clone_dir.parent.parent / ".slideflow_dbt_logs" / clone_dir.name
        )
        if workspace_log_dir.exists() and _is_path_within(
            workspace_log_dir, clone_dir.parent.parent / ".slideflow_dbt_logs"
        ):
            shutil.rmtree(workspace_log_dir)
    except Exception as error:
        logger.warning(
            "Failed to remove evicted DBT clone directory '%s': %s", clone_dir, error
        )


def _cleanup_managed_compile_dir(compiled_dir: Path) -> None:
    """Best-effort removal of one managed dbt compile variant."""
    _drop_manifest_index(compiled_dir)
    managed_root = compiled_dir.parent
    clone_dir = managed_root.parent
    if (
        managed_root.name != ".slideflow_dbt_targets"
        or clone_dir.parent.name != ".slideflow_dbt_clones"
        or not _is_path_within(compiled_dir, managed_root)
    ):
        logger.warning(
            "Refusing to delete unmanaged DBT compile directory: %s", compiled_dir
        )
        return
    if not compiled_dir.exists():
        return
    try:
        shutil.rmtree(compiled_dir)
    except Exception as error:
        logger.warning(
            "Failed to remove evicted DBT compile directory '%s': %s",
            compiled_dir,
            error,
        )


def _source_clone_dir(compiled_dir: Path) -> Path:
    """Resolve the source clone for a managed compile variant."""
    if (
        compiled_dir.parent.name == ".slideflow_dbt_targets"
        and compiled_dir.parent.parent.parent.name == ".slideflow_dbt_clones"
    ):
        return compiled_dir.parent.parent
    return compiled_dir


def _acquire_compiled_project_lease_locked(compiled_dir: Path) -> None:
    """Mark a compiled output directory as actively in use.

    Requires caller to hold _cache_lock.
    """
    _compiled_projects_in_use[compiled_dir] = (
        _compiled_projects_in_use.get(compiled_dir, 0) + 1
    )


def _acquire_prepared_workspace_lease_locked(clone_dir: Path) -> None:
    """Mark a prepared clone as actively used by compilation."""
    _prepared_workspaces_in_use[clone_dir] = (
        _prepared_workspaces_in_use.get(clone_dir, 0) + 1
    )


def _release_prepared_workspace_lease_locked(clone_dir: Path) -> None:
    """Release one prepared-workspace usage lease."""
    current = _prepared_workspaces_in_use.get(clone_dir, 0)
    if current <= 1:
        _prepared_workspaces_in_use.pop(clone_dir, None)
    else:
        _prepared_workspaces_in_use[clone_dir] = current - 1


def _workspace_has_compiled_references_locked(clone_dir: Path) -> bool:
    """Return whether cached or leased compile variants use a workspace."""
    for compiled_dir in _compiled_projects_cache.values():
        if _source_clone_dir(compiled_dir) == clone_dir:
            return True
    for compiled_dir, count in _compiled_projects_in_use.items():
        if count > 0 and _source_clone_dir(compiled_dir) == clone_dir:
            return True
    return False


def _collect_ready_cleanup_dirs_locked() -> tuple[list[Path], list[Path]]:
    """Collect safe compile and workspace cleanup directories.

    Requires caller to hold _cache_lock.
    """
    cached_dirs = set(_compiled_projects_cache.values())
    ready_compiles: list[Path] = []
    for compiled_dir in list(_pending_cleanup_dirs):
        if _compiled_projects_in_use.get(compiled_dir, 0) > 0:
            continue
        if compiled_dir in cached_dirs:
            continue
        _pending_cleanup_dirs.discard(compiled_dir)
        ready_compiles.append(compiled_dir)

    cached_workspaces = set(_prepared_workspaces_cache.values())
    ready_workspaces: list[Path] = []
    for clone_dir in list(_pending_workspace_cleanup_dirs):
        if clone_dir in cached_workspaces:
            continue
        if _prepared_workspaces_in_use.get(clone_dir, 0) > 0:
            continue
        if _workspace_has_compiled_references_locked(clone_dir):
            continue
        _pending_workspace_cleanup_dirs.discard(clone_dir)
        for compiled_dir in list(_pending_cleanup_dirs):
            if _is_path_within(compiled_dir, clone_dir):
                _pending_cleanup_dirs.discard(compiled_dir)
        ready_workspaces.append(clone_dir)
    return ready_compiles, ready_workspaces


def _cleanup_ready_managed_dirs() -> None:
    """Best-effort cleanup for pending compile and workspace directories."""
    with _cache_lock:
        ready_compiles, ready_workspaces = _collect_ready_cleanup_dirs_locked()
    for directory in ready_compiles:
        _cleanup_managed_compile_dir(directory)
    for directory in ready_workspaces:
        _cleanup_managed_clone_dir(directory)


def _cleanup_ready_managed_clone_dirs() -> None:
    """Backward-compatible wrapper for all managed dbt cleanup."""
    _cleanup_ready_managed_dirs()


def _release_compiled_project_lease(compiled_dir: Path) -> None:
    """Release a compiled project lease and cleanup any newly-safe evictions."""
    with _cache_lock:
        current = _compiled_projects_in_use.get(compiled_dir, 0)
        if current <= 1:
            _compiled_projects_in_use.pop(compiled_dir, None)
        else:
            _compiled_projects_in_use[compiled_dir] = current - 1

        ready_compiles, ready_workspaces = _collect_ready_cleanup_dirs_locked()

    for directory in ready_compiles:
        _cleanup_managed_compile_dir(directory)
    for directory in ready_workspaces:
        _cleanup_managed_clone_dir(directory)


def _prune_compiled_projects_cache_locked(max_entries: int) -> None:
    """Prune compiled project cache to max entries. Requires caller lock."""
    while len(_compiled_projects_cache) > max_entries:
        ordered_keys = sorted(
            _compiled_projects_cache.keys(),
            key=lambda cache_key: _compiled_projects_last_access.get(cache_key, 0.0),
        )
        evicted = False
        for oldest_key in ordered_keys:
            compiled_dir = _compiled_projects_cache.get(oldest_key)
            if compiled_dir is None:
                continue
            if _compiled_projects_in_use.get(compiled_dir, 0) > 0:
                continue

            _compiled_projects_cache.pop(oldest_key, None)
            _compiled_projects_last_access.pop(oldest_key, None)
            _compiled_project_coverage.pop(oldest_key, None)
            _selection_locks.pop(oldest_key, None)
            _pending_cleanup_dirs.add(compiled_dir)
            evicted = True
            break

        if not evicted:
            # All cache entries are actively in use. Temporarily exceed max_entries.
            break


def _prune_prepared_workspaces_cache_locked(max_entries: int) -> None:
    """Prune unused prepared workspaces to the shared cache bound."""
    while len(_prepared_workspaces_cache) > max_entries:
        ordered_keys = sorted(
            _prepared_workspaces_cache,
            key=lambda key: _prepared_workspaces_last_access.get(key, 0.0),
        )
        evicted = False
        for oldest_key in ordered_keys:
            clone_dir = _prepared_workspaces_cache.get(oldest_key)
            if clone_dir is None:
                continue
            if _prepared_workspaces_in_use.get(clone_dir, 0) > 0:
                continue
            if _workspace_has_compiled_references_locked(clone_dir):
                continue
            _prepared_workspaces_cache.pop(oldest_key, None)
            _prepared_workspaces_last_access.pop(oldest_key, None)
            _pending_workspace_cleanup_dirs.add(clone_dir)
            evicted = True
            break
        if not evicted:
            break


def _prune_compilation_failures_locked(
    max_entries: int, failure_backoff_s: float
) -> None:
    """Bound and clean stale compile-failure cache entries.

    Requires caller to hold _cache_lock.
    """
    now = time.time()
    if failure_backoff_s <= 0:
        _compilation_failures.clear()
        return

    expired_keys = [
        key
        for key, (failed_at, _message) in _compilation_failures.items()
        if (now - failed_at) >= failure_backoff_s
    ]
    for key in expired_keys:
        _compilation_failures.pop(key, None)

    if len(_compilation_failures) <= max_entries:
        return

    sorted_keys = sorted(
        _compilation_failures.keys(),
        key=lambda key: _compilation_failures[key][0],
    )
    remove_count = len(_compilation_failures) - max_entries
    for key in sorted_keys[:remove_count]:
        _compilation_failures.pop(key, None)


def _ensure_dbt_invoke_success(command: str, invocation_result: Any) -> None:
    """Validate dbtRunner.invoke results and raise on command failures."""
    if invocation_result is None:
        return

    success = getattr(invocation_result, "success", None)
    if success is True:
        return

    if success is False:
        exception = getattr(invocation_result, "exception", None)
        if isinstance(exception, BaseException):
            raise DataSourceError(f"dbt {command} failed: {exception}") from exception
        if exception is not None:
            raise DataSourceError(f"dbt {command} failed: {exception}")
        raise DataSourceError(f"dbt {command} failed.")

    if isinstance(invocation_result, bool) and not invocation_result:
        raise DataSourceError(f"dbt {command} failed.")


def _build_clone_identity_key(
    package_url: str,
    branch: Optional[str],
    target: Optional[str] = None,
    vars: Optional[dict[str, Any]] = None,
    profiles_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
) -> str:
    """Build a deterministic identity key for shared DBT workspaces.

    ``target`` and ``vars`` remain accepted for internal compatibility but are
    deliberately excluded: they affect compilation artifacts, not repository
    checkout or dependency installation.
    """
    payload = {
        "package_url": package_url,
        "branch": branch or "default",
        "profiles_dir": profiles_dir or "",
        "profile_name": profile_name or "",
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]


def _workspace_cache_key(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    profiles_dir: Optional[str],
    profile_name: Optional[str],
) -> tuple:
    """Return the identity for clone and dependency preparation."""
    return (
        package_url,
        _canonical_project_dir(project_dir),
        branch,
        _canonical_profiles_dir(profiles_dir),
        profile_name,
    )


def _project_cache_key(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str],
    profile_name: Optional[str],
) -> tuple:
    """Return the identity for one isolated compiled artifact variant."""
    return _workspace_cache_key(
        package_url,
        project_dir,
        branch,
        profiles_dir,
        profile_name,
    ) + (
        target,
        json.dumps(vars or {}, sort_keys=True),
    )


def _build_compile_identity_key(target: str, vars: Optional[dict[str, Any]]) -> str:
    """Build a deterministic directory key for one compile variant."""
    payload = {"target": target, "vars": vars or {}}
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]


def _resolve_managed_clone_dir(
    project_dir: str,
    package_url: str,
    branch: Optional[str],
    target: Optional[str] = None,
    vars: Optional[dict[str, Any]] = None,
    profiles_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
) -> Path:
    """Resolve a safe managed clone directory under project_dir.

    The user-provided project_dir is treated as a workspace root only.
    Slideflow clones into project_dir/.slideflow_dbt_clones/<key>/ to avoid
    destructive operations against arbitrary user directories.
    """
    workspace_root = Path(project_dir).expanduser().resolve()
    protected_roots = {Path("/"), Path.home().resolve(), Path.cwd().resolve()}
    if workspace_root in protected_roots:
        raise DataSourceError(
            "Refusing to use a protected project_dir for DBT clones: "
            f"{workspace_root}. Use a dedicated workspace directory."
        )

    managed_root = workspace_root / ".slideflow_dbt_clones"
    managed_root.mkdir(parents=True, exist_ok=True)
    key = _build_clone_identity_key(
        package_url=package_url,
        branch=branch,
        profiles_dir=profiles_dir,
        profile_name=profile_name,
    )
    return managed_root / key


def _resolve_managed_compile_dir(
    clone_dir: Path,
    target: str,
    vars: Optional[dict[str, Any]],
) -> Path:
    """Resolve the isolated artifact root for one target/vars combination."""
    managed_root = clone_dir / ".slideflow_dbt_targets"
    if managed_root.is_symlink() or (
        managed_root.exists() and not managed_root.is_dir()
    ):
        raise DataSourceError(
            "Reserved DBT compile path must be a real directory: " f"{managed_root}"
        )
    key = _build_compile_identity_key(target, vars)
    return managed_root / key


def _resolve_existing_compiled_project_dir(
    project_dir: str,
    *,
    acquire_lease: bool = False,
) -> Path:
    """Resolve and validate an existing compiled dbt project directory."""
    compiled_project_dir = Path(project_dir).expanduser().resolve()
    manifest_path = compiled_project_dir / "target" / "manifest.json"
    if not manifest_path.is_file():
        raise DataSourceError(
            "dbt compile:false requires an existing compiled dbt project at "
            f"{compiled_project_dir}. Expected manifest at {manifest_path}. "
            "Run `dbt deps` and `dbt compile` first, or set compile:true to let "
            "Slideflow clone and compile the project."
        )

    if acquire_lease:
        with _cache_lock:
            _acquire_compiled_project_lease_locked(compiled_project_dir)
    return compiled_project_dir


def _prepare_profiles(clone_dir: Path, profiles_dir: Optional[str]) -> None:
    """Copy configured profiles into a prepared clone once."""
    if not profiles_dir:
        return
    try:
        src = Path(profiles_dir)
        if src.is_dir():
            candidate = src / "profiles.yml"
            if candidate.exists():
                shutil.copy2(candidate, clone_dir / "profiles.yml")
            else:
                for profile_file in src.glob("*.y*ml"):
                    shutil.copy2(profile_file, clone_dir / profile_file.name)
        elif src.is_file():
            destination = clone_dir / (
                "profiles.yml" if src.name != "profiles.yml" else src.name
            )
            shutil.copy2(src, destination)
        else:
            logger.warning("profiles_dir path not found: %s", profiles_dir)
    except Exception as error:
        logger.warning(
            "Failed to prepare dbt profiles from %s: %s",
            profiles_dir,
            error,
            exc_info=True,
        )


def _get_prepared_workspace(
    *,
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    profiles_dir: Optional[str],
    profile_name: Optional[str],
    acquire_lease: bool = False,
) -> Path:
    """Clone a dbt repository and install dependencies once per workspace."""
    cache_key = _workspace_cache_key(
        package_url, project_dir, branch, profiles_dir, profile_name
    )
    failure_key = ("workspace",) + cache_key
    max_cache_entries = _resolve_dbt_cache_max_entries()
    failure_backoff_s = _resolve_dbt_compile_failure_backoff_seconds()
    failure_cache_max_entries = _resolve_dbt_failure_cache_max_entries()

    while True:
        with _cache_lock:
            _prune_compilation_failures_locked(
                max_entries=failure_cache_max_entries,
                failure_backoff_s=failure_backoff_s,
            )
            cached_dir = _prepared_workspaces_cache.get(cache_key)
            if cached_dir is not None:
                if cached_dir.exists():
                    _prepared_workspaces_last_access[cache_key] = time.time()
                    if acquire_lease:
                        _acquire_prepared_workspace_lease_locked(cached_dir)
                    return cached_dir
                _drop_manifest_indexes_under_locked(cached_dir)
                _prepared_workspaces_cache.pop(cache_key, None)
                _prepared_workspaces_last_access.pop(cache_key, None)

            failure_entry = _compilation_failures.get(failure_key)
            if failure_entry is not None:
                raise DataSourceError(failure_entry[1])

            pending = _workspace_preparation_inflight.get(cache_key)
            if pending is None:
                pending = threading.Event()
                _workspace_preparation_inflight[cache_key] = pending
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            pending.wait()
            continue

        clone_dir: Optional[Path] = None
        try:
            clone_dir = _resolve_managed_clone_dir(
                project_dir=project_dir,
                package_url=package_url,
                branch=branch,
                profiles_dir=profiles_dir,
                profile_name=profile_name,
            )
            with _cache_lock:
                _pending_workspace_cleanup_dirs.discard(clone_dir)
            _clone_repo(package_url, clone_dir, branch)
            reserved_targets = clone_dir / ".slideflow_dbt_targets"
            if reserved_targets.exists() or reserved_targets.is_symlink():
                raise DataSourceError(
                    "DBT repository contains reserved Slideflow path "
                    f"{reserved_targets}. Remove it from the repository."
                )
            _prepare_profiles(clone_dir, profiles_dir)

            runner = _require_dbt_runner_class()()
            deps_args = [
                "deps",
                "--project-dir",
                str(clone_dir),
                "--log-path",
                str(
                    clone_dir.parent.parent
                    / ".slideflow_dbt_logs"
                    / clone_dir.name
                    / "deps"
                ),
            ]
            if profile_name:
                deps_args.extend(["--profile", profile_name])
            if profiles_dir or (clone_dir / "profiles.yml").exists():
                deps_args.extend(["--profiles-dir", str(clone_dir)])

            deps_started = time.time()
            with _dbt_invocation_lock:
                deps_result = runner.invoke(deps_args)
            _ensure_dbt_invoke_success("deps", deps_result)
            log_performance("dbt_deps", time.time() - deps_started, project=package_url)
        except BaseException as error:
            failure_message = str(error) or type(error).__name__
            with _cache_lock:
                _compilation_failures[failure_key] = (time.time(), failure_message)
                _prune_compilation_failures_locked(
                    max_entries=failure_cache_max_entries,
                    failure_backoff_s=failure_backoff_s,
                )
                event = _workspace_preparation_inflight.pop(cache_key, None)
                if event is not None:
                    event.set()
            if clone_dir is not None:
                _cleanup_managed_clone_dir(clone_dir)
            raise

        assert clone_dir is not None
        with _cache_lock:
            _prepared_workspaces_cache[cache_key] = clone_dir
            _prepared_workspaces_last_access[cache_key] = time.time()
            _compilation_failures.pop(failure_key, None)
            if acquire_lease:
                _acquire_prepared_workspace_lease_locked(clone_dir)
            event = _workspace_preparation_inflight.pop(cache_key, None)
            if event is not None:
                event.set()
            _prune_prepared_workspaces_cache_locked(max_cache_entries)
        _cleanup_ready_managed_dirs()
        return clone_dir


def _get_compiled_project(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
    compile: bool = Defaults.DBT_COMPILE,
    acquire_lease: bool = False,
    parse_only: bool = False,
) -> Path:
    """Return isolated artifacts backed by a shared prepared DBT workspace."""
    canonical_project_dir = _canonical_project_dir(project_dir)
    if not compile:
        return _resolve_existing_compiled_project_dir(
            canonical_project_dir,
            acquire_lease=acquire_lease,
        )

    canonical_profiles_dir = _canonical_profiles_dir(profiles_dir)
    cache_key = _project_cache_key(
        package_url,
        canonical_project_dir,
        branch,
        target,
        vars,
        canonical_profiles_dir,
        profile_name,
    )
    failure_key = ("compile",) + cache_key

    max_cache_entries = _resolve_dbt_cache_max_entries()
    failure_backoff_s = _resolve_dbt_compile_failure_backoff_seconds()
    failure_cache_max_entries = _resolve_dbt_failure_cache_max_entries()

    while True:
        with _cache_lock:
            _prune_compilation_failures_locked(
                max_entries=failure_cache_max_entries,
                failure_backoff_s=failure_backoff_s,
            )
            cached_dir = _compiled_projects_cache.get(cache_key)
            if cached_dir is not None:
                if cached_dir.exists():
                    _compiled_projects_last_access[cache_key] = time.time()
                    if acquire_lease:
                        _acquire_compiled_project_lease_locked(cached_dir)
                    return cached_dir
                _drop_manifest_index_locked(cached_dir)
                _compiled_projects_cache.pop(cache_key, None)
                _compiled_projects_last_access.pop(cache_key, None)
                _compiled_project_coverage.pop(cache_key, None)

            failure_entry = _compilation_failures.get(failure_key)
            if failure_entry is not None:
                _failed_at, failure_message = failure_entry
                raise DataSourceError(failure_message)

            pending = _compilation_inflight.get(cache_key)
            if pending is None:
                pending = threading.Event()
                _compilation_inflight[cache_key] = pending
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            pending.wait()
            continue

        compiled_dir: Optional[Path] = None
        clone_dir: Optional[Path] = None
        workspace_leased = False
        try:
            clone_dir = _get_prepared_workspace(
                package_url=package_url,
                project_dir=canonical_project_dir,
                branch=branch,
                profiles_dir=canonical_profiles_dir,
                profile_name=profile_name,
                acquire_lease=True,
            )
            workspace_leased = True
            compiled_dir = _resolve_managed_compile_dir(clone_dir, target, vars)
            with _cache_lock:
                _pending_cleanup_dirs.discard(compiled_dir)
            if compiled_dir.exists():
                _cleanup_managed_compile_dir(compiled_dir)
            compiled_dir.mkdir(parents=True, exist_ok=True)

            runner = _require_dbt_runner_class()()
            compile_start = time.time()
            command = "parse" if parse_only else "compile"
            args = [
                command,
                "--project-dir",
                str(clone_dir),
                "--target",
                target,
                "--target-path",
                str(compiled_dir / "target"),
                "--log-path",
                str(compiled_dir / "logs"),
            ]
            if profiles_dir or (clone_dir / "profiles.yml").exists():
                args.extend(["--profiles-dir", str(clone_dir)])
            if profile_name:
                args.extend(["--profile", profile_name])
            if vars:
                args += ["--vars", json.dumps(vars)]
            with _dbt_invocation_lock:
                compile_result = runner.invoke(args)
            _ensure_dbt_invoke_success(command, compile_result)
            _drop_manifest_index(compiled_dir)
            compile_duration = time.time() - compile_start
            log_performance(
                f"dbt_{command}",
                compile_duration,
                project=package_url,
                target=target,
                vars_count=len(vars) if vars else 0,
            )
        except BaseException as error:
            failure_message = str(error) or type(error).__name__
            with _cache_lock:
                _compilation_failures[failure_key] = (time.time(), failure_message)
                _prune_compilation_failures_locked(
                    max_entries=failure_cache_max_entries,
                    failure_backoff_s=failure_backoff_s,
                )
                event = _compilation_inflight.pop(cache_key, None)
                if event is not None:
                    event.set()
                if workspace_leased and clone_dir is not None:
                    _release_prepared_workspace_lease_locked(clone_dir)
                _prune_prepared_workspaces_cache_locked(max_cache_entries)
            if compiled_dir is not None:
                _cleanup_managed_compile_dir(compiled_dir)
            _cleanup_ready_managed_dirs()
            raise

        assert compiled_dir is not None
        with _cache_lock:
            _compiled_projects_cache[cache_key] = compiled_dir
            _compiled_project_coverage[cache_key] = (
                frozenset() if parse_only else frozenset({"*"})
            )
            _compiled_projects_last_access[cache_key] = time.time()
            _compilation_failures.pop(failure_key, None)
            _prune_compiled_projects_cache_locked(max_cache_entries)
            if acquire_lease:
                _acquire_compiled_project_lease_locked(compiled_dir)
            if workspace_leased and clone_dir is not None:
                _release_prepared_workspace_lease_locked(clone_dir)
            _prune_prepared_workspaces_cache_locked(max_cache_entries)
            event = _compilation_inflight.pop(cache_key, None)
            if event is not None:
                event.set()
        _cleanup_ready_managed_dirs()

        return compiled_dir


def _ensure_selected_compilation(
    *,
    clone_dir: Path,
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str],
    profile_name: Optional[str],
    selectors: tuple[str, ...],
) -> None:
    """Compile the deterministic union of requested selectors once per project."""
    normalized = tuple(sorted(set(selectors)))
    if not normalized:
        return
    cache_key = _project_cache_key(
        package_url,
        project_dir,
        branch,
        target,
        vars,
        profiles_dir,
        profile_name,
    )
    with _cache_lock:
        selection_lock = _selection_locks.setdefault(cache_key, threading.Lock())

    with selection_lock:
        with _cache_lock:
            coverage = _compiled_project_coverage.get(cache_key, frozenset())
        if "*" in coverage or set(normalized).issubset(coverage):
            return

        union = tuple(sorted(set(coverage).union(normalized)))
        failure_key = ("selected",) + cache_key + (union,)
        failure_backoff_s = _resolve_dbt_compile_failure_backoff_seconds()
        failure_cache_max_entries = _resolve_dbt_failure_cache_max_entries()
        with _cache_lock:
            _prune_compilation_failures_locked(
                max_entries=failure_cache_max_entries,
                failure_backoff_s=failure_backoff_s,
            )
            failure_entry = _compilation_failures.get(failure_key)
        if failure_entry is not None:
            raise DataSourceError(failure_entry[1])

        compiled_dir = clone_dir
        source_dir = _source_clone_dir(compiled_dir)
        runner = _require_dbt_runner_class()()
        args = [
            "compile",
            "--project-dir",
            str(source_dir),
            "--target",
            target,
            "--target-path",
            str(compiled_dir / "target"),
            "--log-path",
            str(compiled_dir / "logs"),
            "--select",
            " ".join(union),
        ]
        project_profiles_path = source_dir / "profiles.yml"
        if profiles_dir or project_profiles_path.exists():
            args.extend(["--profiles-dir", str(source_dir)])
        if profile_name:
            args.extend(["--profile", profile_name])
        if vars:
            args.extend(["--vars", json.dumps(vars)])

        started = time.time()
        try:
            with _dbt_invocation_lock:
                result = runner.invoke(args)
            _ensure_dbt_invoke_success("compile", result)
            _drop_manifest_index(compiled_dir)
        except BaseException as error:
            failure_message = str(error) or type(error).__name__
            with _cache_lock:
                _compilation_failures[failure_key] = (time.time(), failure_message)
                _prune_compilation_failures_locked(
                    max_entries=failure_cache_max_entries,
                    failure_backoff_s=failure_backoff_s,
                )
            raise

        log_performance(
            "dbt_compile",
            time.time() - started,
            project=package_url,
            target=target,
            vars_count=len(vars) if vars else 0,
            selection_count=len(union),
        )
        with _cache_lock:
            _compiled_project_coverage[cache_key] = frozenset(union)
            _compilation_failures.pop(failure_key, None)


@contextmanager
def _compiled_project_lease(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
    compile: bool = Defaults.DBT_COMPILE,
    parse_only: bool = False,
) -> Iterator[Path]:
    """Acquire a temporary usage lease for a compiled DBT clone directory."""
    clone_dir = _get_compiled_project(
        package_url=package_url,
        project_dir=project_dir,
        branch=branch,
        target=target,
        vars=vars,
        profiles_dir=profiles_dir,
        profile_name=profile_name,
        compile=compile,
        acquire_lease=True,
        parse_only=parse_only,
    )
    try:
        yield clone_dir
    finally:
        _release_compiled_project_lease(clone_dir)


def _resolve_model_from_index(
    manifest_index: _ManifestIndex,
    model_name: str,
    *,
    model_unique_id: Optional[str] = None,
    model_package_name: Optional[str] = None,
    model_selector_name: Optional[str] = None,
) -> Optional[_ManifestNodeIndexEntry]:
    candidates = list(manifest_index.by_alias.get(model_name, []))
    if not candidates:
        return None
    selector_context = _format_selector_context(
        model_unique_id=model_unique_id,
        model_package_name=model_package_name,
        model_name=model_selector_name,
    )
    if model_unique_id:
        unique_candidate = manifest_index.by_unique_id.get(model_unique_id)
        if unique_candidate is None:
            raise DataSourceError(
                f"No dbt node with unique_id '{model_unique_id}' for alias "
                f"'{model_name}'."
            )
        if unique_candidate.alias != model_name:
            raise DataSourceError(
                f"unique_id '{model_unique_id}' resolved to alias "
                f"'{unique_candidate.alias}', expected '{model_name}'."
            )
        candidates = [unique_candidate]
    if model_package_name:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.package_name == model_package_name
        ]
    if model_selector_name:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.model_name == model_selector_name
        ]
    if not candidates:
        raise DataSourceError(
            f"No dbt model found for alias '{model_name}'{selector_context}."
        )
    if len(candidates) > 1:
        rendered_candidates = ", ".join(
            _format_manifest_candidate(candidate) for candidate in candidates
        )
        raise DataSourceError(
            f"Ambiguous dbt model alias '{model_name}'. Provide one of "
            "`model_unique_id`, `model_package_name`, or `model_selector_name` "
            f"to disambiguate. Candidates: {rendered_candidates}"
        )
    return candidates[0]


def _exact_selector(node: _ManifestNodeIndexEntry) -> str:
    unique_id_parts = node.unique_id.split(".")
    package_name = node.package_name
    model_name = node.model_name
    if len(unique_id_parts) >= 3:
        package_name = package_name or unique_id_parts[-2]
        model_name = model_name or unique_id_parts[-1]
    if not model_name:
        raise DataSourceError(
            f"dbt node '{node.unique_id}' is missing a selector-compatible name."
        )
    return f"{package_name}.{model_name}" if package_name else model_name


class DBTManifestConnector(BaseModel, DataConnector):
    """Connector for parsing DBT manifest files and extracting compiled SQL.

    This connector handles the compilation of DBT projects and parsing of
    manifest.json files to extract compiled SQL queries for specific models.
    It does not execute queries directly but provides the compiled SQL for
    use by other connectors.

    The connector manages the full DBT workflow:
    1. Clone the Git repository
    2. Install DBT dependencies
    3. Compile the project
    4. Parse the manifest to find model SQL

    Attributes:
        package_url: Git URL of the DBT project repository.
        project_dir: Local directory path for cloning the project.
        profile_name: Optional dbt profile name to override project default.
        branch: Optional Git branch to checkout.
        target: DBT target environment for compilation.
        vars: Optional variables to pass to DBT compilation.
        compile: Whether to compile the project (usually True).

    Example:
        >>> connector = DBTManifestConnector(
        ...     package_url="https://github.com/company/dbt-project.git",
        ...     project_dir="/tmp/dbt_project",
        ...     target="prod"
        ... )
        >>> sql = connector.get_compiled_query("revenue_model")
    """

    package_url: str = Field(..., description="Git URL of dbt project")
    project_dir: str = Field(..., description="Local path to dbt project")
    profile_name: Optional[str] = Field(
        None, description="dbt profile name to override the one in dbt_project.yml"
    )
    branch: Optional[str] = Field(None, description="Git branch to checkout")
    target: str = Field(Defaults.DBT_TARGET, description="dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description="dbt vars")
    profiles_dir: Optional[str] = Field(
        None,
        description="Optional path to a dbt profiles directory or profiles.yml to use. If provided, it will be copied into the cloned project directory before running dbt.",
    )
    compile: bool = Field(
        Defaults.DBT_COMPILE, description="Whether to compile project"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    def prepare_models(
        self,
        requests: Sequence[tuple[str, Optional[str], Optional[str], Optional[str]]],
    ) -> None:
        """Resolve and compile one exact, normalized model batch."""
        if not self.compile or not requests:
            return
        with _compiled_project_lease(
            package_url=self.package_url,
            project_dir=self.project_dir,
            branch=self.branch,
            target=self.target,
            vars=self.vars,
            profiles_dir=self.profiles_dir,
            profile_name=self.profile_name,
            compile=True,
            parse_only=True,
        ) as clone_dir:
            manifest_index = _get_manifest_index(clone_dir)
            selections: list[_ManifestNodeIndexEntry] = []
            for alias, unique_id, package_name, selector_name in requests:
                selection = _resolve_model_from_index(
                    manifest_index,
                    alias,
                    model_unique_id=unique_id,
                    model_package_name=package_name,
                    model_selector_name=selector_name,
                )
                if selection is None:
                    raise DataSourceError(f"No dbt model found for alias '{alias}'.")
                selections.append(selection)
            selectors = tuple(_exact_selector(selection) for selection in selections)
            _ensure_selected_compilation(
                clone_dir=clone_dir,
                package_url=self.package_url,
                project_dir=self.project_dir,
                branch=self.branch,
                target=self.target,
                vars=self.vars,
                profiles_dir=self.profiles_dir,
                profile_name=self.profile_name,
                selectors=selectors,
            )
            refreshed = _get_manifest_index(clone_dir)
            missing = []
            for selection in selections:
                compiled = refreshed.by_unique_id.get(selection.unique_id)
                if compiled is None or compiled.compiled_path is None:
                    missing.append(selection.unique_id)
                    continue
                if not (clone_dir / compiled.compiled_path).is_file():
                    missing.append(selection.unique_id)
            if missing:
                raise DataSourceError(
                    "Scoped dbt compilation omitted expected nodes: "
                    + ", ".join(sorted(missing))
                )

    def get_compiled_query(
        self,
        model_name: str,
        *,
        model_unique_id: Optional[str] = None,
        model_package_name: Optional[str] = None,
        model_selector_name: Optional[str] = None,
    ) -> Optional[str]:
        """Extract compiled SQL query for a specific DBT model alias."""
        model_info = self.get_compiled_model_info(
            model_name,
            model_unique_id=model_unique_id,
            model_package_name=model_package_name,
            model_selector_name=model_selector_name,
        )
        return model_info.sql_text if model_info else None

    def get_compiled_model_info(
        self,
        model_name: str,
        *,
        model_unique_id: Optional[str] = None,
        model_package_name: Optional[str] = None,
        model_selector_name: Optional[str] = None,
    ) -> Optional[DBTCompiledModelInfo]:
        """Extract compiled SQL and manifest metadata for a specific dbt model."""
        with _compiled_project_lease(
            package_url=self.package_url,
            project_dir=self.project_dir,
            branch=self.branch,
            target=self.target,
            vars=self.vars,
            profiles_dir=self.profiles_dir,
            profile_name=self.profile_name,
            compile=self.compile,
            parse_only=self.compile,
        ) as clone_dir:
            manifest_index = _get_manifest_index(clone_dir)
            selected = _resolve_model_from_index(
                manifest_index,
                model_name,
                model_unique_id=model_unique_id,
                model_package_name=model_package_name,
                model_selector_name=model_selector_name,
            )
            if selected is None:
                return None
            if self.compile:
                _ensure_selected_compilation(
                    clone_dir=clone_dir,
                    package_url=self.package_url,
                    project_dir=self.project_dir,
                    branch=self.branch,
                    target=self.target,
                    vars=self.vars,
                    profiles_dir=self.profiles_dir,
                    profile_name=self.profile_name,
                    selectors=(_exact_selector(selected),),
                )
                refreshed_index = _get_manifest_index(clone_dir)
                refreshed = refreshed_index.by_unique_id.get(selected.unique_id)
                if refreshed is None:
                    raise DataSourceError(
                        "Scoped dbt compilation did not retain expected node "
                        f"'{selected.unique_id}' in manifest.json."
                    )
                selected = refreshed
            full = (
                clone_dir / selected.compiled_path
                if selected.compiled_path is not None
                else None
            )
            if full and full.exists():
                sql_text = full.read_text()
                repo_url = canonical_repo_web_url(self.package_url)
                ref = _resolve_repo_ref(_source_clone_dir(clone_dir), self.branch)
                file_url = build_repo_file_url(
                    repo_web_url=repo_url,
                    ref=ref,
                    file_path=selected.original_file_path,
                )
                return DBTCompiledModelInfo(
                    sql_text=sql_text,
                    unique_id=selected.unique_id,
                    alias=selected.alias,
                    package_name=selected.package_name,
                    model_name=selected.model_name,
                    compiled_path=selected.compiled_path,
                    model_path=selected.original_file_path,
                    repo_url=repo_url,
                    file_url=file_url,
                    ref=ref,
                )

            logger.warning(
                "Missing compiled file for %s: %s",
                selected.alias,
                selected.compiled_path,
            )
            if not self.compile:
                raise DataSourceError(
                    "dbt compile:false requires compiled SQL files referenced by "
                    f"manifest.json. Missing compiled file for alias "
                    f"'{selected.alias}': {selected.compiled_path}. Run `dbt compile` "
                    "for this project, or set compile:true to let Slideflow compile it."
                )
            return None

    def fetch_data(self) -> pd.DataFrame:
        """Not implemented for manifest connector.

        DBTManifestConnector is designed for extracting compiled SQL queries,
        not for executing them and fetching data. Use get_compiled_query()
        to retrieve SQL, then pass it to a query execution connector.

        Raises:
            NotImplementedError: Always, as this method is not applicable.

        Example:
            >>> # Correct usage
            >>> sql = connector.get_compiled_query("model_name")
            >>> db_connector = DatabricksConnector(sql)
            >>> data = db_connector.fetch_data()
        """
        raise NotImplementedError(
            "DBTManifestConnector is for manifest parsing, not data fetching. Use get_compiled_query() instead."
        )


class _DBTWarehouseConnectorBase(BaseModel, DataConnector):
    """Shared DBT manifest compilation + warehouse execution flow."""

    model_alias: str
    model_unique_id: Optional[str] = None
    model_package_name: Optional[str] = None
    model_selector_name: Optional[str] = None
    package_url: str
    project_dir: str
    profile_name: Optional[str] = None
    branch: Optional[str] = None
    target: str = Defaults.DBT_TARGET
    vars: Optional[dict[str, Any]] = None
    compile: bool = Defaults.DBT_COMPILE
    profiles_dir: Optional[str] = None
    _manifest_connector: Optional[DBTManifestConnector] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        if self._manifest_connector is None:
            self._manifest_connector = self._create_manifest_connector()

    def _create_manifest_connector(self) -> DBTManifestConnector:
        return DBTManifestConnector(
            package_url=self.package_url,
            project_dir=self.project_dir,
            branch=self.branch,
            target=self.target,
            vars=self.vars,
            profiles_dir=self.profiles_dir,
            compile=self.compile,
            profile_name=self.profile_name,
        )

    def _resolve_compiled_sql(self) -> str:
        if self._manifest_connector is None:
            self._manifest_connector = self._create_manifest_connector()

        sql_text = self._manifest_connector.get_compiled_query(
            self.model_alias,
            model_unique_id=self.model_unique_id,
            model_package_name=self.model_package_name,
            model_selector_name=self.model_selector_name,
        )
        if not sql_text:
            raise DataSourceError(f"No compiled model '{self.model_alias}'")
        return sql_text

    def _create_sql_executor(self) -> SQLExecutor:
        raise NotImplementedError

    def fetch_data(self) -> pd.DataFrame:
        """Compile DBT model and execute it on the configured warehouse."""
        sql_text = self._resolve_compiled_sql()
        executor = self._create_sql_executor()
        bind = getattr(executor, "set_query_controller", None)
        if callable(bind):
            bind(getattr(self, "_query_controller", None))
        return executor.execute(sql_text)


class DBTDatabricksConnector(_DBTWarehouseConnectorBase):
    """Connector that combines DBT model compilation with Databricks execution.

    This connector bridges DBT transformations with Databricks SQL execution.
    It compiles DBT models to SQL and executes them against Databricks SQL
    warehouses, providing a complete data transformation and retrieval pipeline.

    The connector handles the full workflow:
    1. Compile the DBT project and extract model SQL
    2. Execute the compiled SQL against Databricks
    3. Return results as a pandas DataFrame

    Attributes:
        model_alias: The alias of the DBT model to execute.
        package_url: Git URL of the DBT project repository.
        project_dir: Local directory path for cloning the project.
        profile_name: Optional dbt profile name to override project default.
        branch: Optional Git branch to checkout.
        target: DBT target environment for compilation.
        vars: Optional variables to pass to DBT compilation.
        compile: Whether to compile the project.
        profiles_dir: Optional path to dbt profiles directory/file.

    Example:
        >>> connector = DBTDatabricksConnector(
        ...     model_alias="monthly_revenue",
        ...     package_url="https://github.com/company/dbt-project.git",
        ...     project_dir="/tmp/dbt_project",
        ...     target="prod"
        ... )
        >>> data = connector.fetch_data()
        >>> print(f"Retrieved {len(data)} rows from DBT model")
    """

    sql_executor_factory: ClassVar[Callable[[], SQLExecutor]] = (
        _create_databricks_sql_executor
    )

    def _create_sql_executor(self) -> SQLExecutor:
        return type(self).sql_executor_factory()


class DBTBigQueryConnector(_DBTWarehouseConnectorBase):
    """Connector that combines DBT model compilation with BigQuery execution."""

    project_id: Optional[str] = None
    location: Optional[str] = None
    credentials_json: Optional[str] = None
    credentials_path: Optional[str] = None
    timeout: Optional[int] = None

    def _create_sql_executor(self) -> SQLExecutor:
        return BigQuerySQLExecutor(
            project_id=self.project_id,
            location=self.location,
            credentials_json=self.credentials_json,
            credentials_path=self.credentials_path,
            timeout=self.timeout,
        )


class DBTDuckDBConnector(_DBTWarehouseConnectorBase):
    """Connector that combines DBT model compilation with DuckDB execution."""

    database: str
    read_only: bool = True
    file_search_path: Optional[str | list[str]] = None

    def _create_sql_executor(self) -> SQLExecutor:
        return DuckDBSQLExecutor(
            database=self.database,
            read_only=self.read_only,
            file_search_path=self.file_search_path,
        )


class DBTRedshiftConnector(_DBTWarehouseConnectorBase):
    """Connector that combines DBT model compilation with Redshift execution."""

    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    iam: Optional[bool] = None
    db_user: Optional[str] = None
    cluster_identifier: Optional[str] = None
    region: Optional[str] = None
    profile: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    is_serverless: Optional[bool] = None
    serverless_acct_id: Optional[str] = None
    serverless_work_group: Optional[str] = None
    ssl: Optional[bool] = None
    sslmode: Optional[str] = None
    timeout: Optional[int] = None
    application_name: Optional[str] = None
    connection_options: Optional[dict[str, Any]] = None

    def _create_sql_executor(self) -> SQLExecutor:
        return RedshiftSQLExecutor(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            iam=self.iam,
            db_user=self.db_user,
            cluster_identifier=self.cluster_identifier,
            region=self.region,
            profile=self.profile,
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            session_token=self.session_token,
            is_serverless=self.is_serverless,
            serverless_acct_id=self.serverless_acct_id,
            serverless_work_group=self.serverless_work_group,
            ssl=self.ssl,
            sslmode=self.sslmode,
            timeout=self.timeout,
            application_name=self.application_name,
            connection_options=self.connection_options,
        )


def _build_dbt_citation_entries(
    *,
    source_name: str,
    provider: str,
    mode: str,
    model_info: Optional[DBTCompiledModelInfo],
    execution_metadata: Optional[dict[str, Any]] = None,
    include_query_text: bool = False,
) -> list[CitationEntry]:
    """Build model/execution citation entries for dbt-backed sources."""
    normalized_mode = mode if mode in {"model", "execution", "both"} else "model"
    entries: list[CitationEntry] = []

    if model_info and normalized_mode in {"model", "both"}:
        model_source_id = (
            f"{provider}:{source_name}:model:{model_info.unique_id}:{model_info.ref}"
        )
        entries.append(
            CitationEntry(
                source_id=model_source_id,
                provider=provider,
                display_name=f"{source_name} (dbt model)",
                repo_url=model_info.repo_url,
                file_url=model_info.file_url,
                model_unique_id=model_info.unique_id,
                model_path=model_info.model_path,
                metadata={
                    "alias": model_info.alias,
                    "package_name": model_info.package_name,
                    "model_name": model_info.model_name,
                    "ref": model_info.ref,
                },
            )
        )

    if model_info and normalized_mode in {"execution", "both"}:
        query_fingerprint = fingerprint_text(model_info.sql_text)
        execution_source_id = (
            f"{provider}:{source_name}:execution:{query_fingerprint}:{model_info.ref}"
        )
        metadata = dict(execution_metadata or {})
        metadata["query_fingerprint"] = query_fingerprint
        metadata["ref"] = model_info.ref
        if include_query_text:
            metadata["query_text"] = model_info.sql_text
        entries.append(
            CitationEntry(
                source_id=execution_source_id,
                provider=provider,
                display_name=f"{source_name} (dbt execution)",
                model_unique_id=model_info.unique_id,
                model_path=model_info.model_path,
                query_fingerprint=query_fingerprint,
                metadata=metadata,
            )
        )

    if entries:
        return entries

    fallback_source_id = (
        f"{provider}:{source_name}:dbt:{fingerprint_text(f'{provider}|{source_name}')}"
    )
    return [
        CitationEntry(
            source_id=fallback_source_id,
            provider=provider,
            display_name=f"{source_name} (dbt source)",
        )
    ]


class DBTDatabricksSourceConfig(BaseSourceConfig):
    """Configuration model for DBT models executed on Databricks.

    This configuration class defines the parameters needed to compile DBT
    models and execute them against Databricks SQL warehouses. It combines
    DBT's transformation capabilities with Databricks' execution power.

    The configuration handles the complete DBT-to-Databricks pipeline,
    including Git repository management, project compilation, and query
    execution. It integrates with the discriminated union system for
    polymorphic data source configurations.

    Attributes:
        type: Always "databricks_dbt" for DBT-Databricks data sources.
        model_alias: The alias of the DBT model to execute.
        package_url: Git URL of the DBT project repository.
        project_dir: Local directory path for cloning the project.
        profile_name: Optional dbt profile name to override project default.
        branch: Optional Git branch to checkout.
        target: DBT target environment for compilation.
        vars: Optional variables to pass to DBT compilation.
        compile: Whether to compile the project before execution.
        connector_class: References DBTDatabricksConnector for instantiation.

    Example:
        Creating a DBT-Databricks data source configuration:

        >>> config = DBTDatabricksSourceConfig(
        ...     name="revenue_analytics",
        ...     type="databricks_dbt",
        ...     model_alias="monthly_revenue_by_region",
        ...     package_url="https://github.com/company/analytics-dbt.git",
        ...     project_dir="/tmp/analytics_dbt",
        ...     branch="production",
        ...     target="prod",
        ...     vars={"start_date": "2024-01-01", "end_date": "2024-12-31"}
        ... )
        >>>
        >>> # Use configuration to fetch transformed data
        >>> data = config.fetch_data()
        >>> print(f"Retrieved {len(data)} rows from DBT model")

        From dictionary/JSON:

        >>> config_dict = {
        ...     "name": "user_metrics",
        ...     "type": "databricks_dbt",
        ...     "model_alias": "daily_active_users",
        ...     "package_url": "https://github.com/company/metrics-dbt.git",
        ...     "project_dir": "/tmp/metrics_dbt",
        ...     "target": "prod"
        ... }
        >>> config = DBTDatabricksSourceConfig(
        ...     name="user_metrics",
        ...     type="databricks_dbt",
        ...     model_alias="daily_active_users",
        ...     package_url="https://github.com/company/metrics-dbt.git",
        ...     project_dir="/tmp/metrics_dbt",
        ...     target="prod",
        ...     profile_name="my_alternate_profile"
        ... )
        >>> config = DBTDatabricksSourceConfig(**config_dict)
    """

    type: Literal["databricks_dbt"] = Field(
        "databricks_dbt", description="dbt + Databricks data source"
    )
    model_alias: str = Field(..., description="dbt model alias")
    model_unique_id: Optional[str] = Field(
        None, description="Optional dbt unique_id selector for alias disambiguation"
    )
    model_package_name: Optional[str] = Field(
        None, description="Optional dbt package_name selector for alias disambiguation"
    )
    model_selector_name: Optional[str] = Field(
        None, description="Optional dbt model name selector for alias disambiguation"
    )
    package_url: str = Field(..., description="Git URL of dbt project")
    project_dir: str = Field(..., description="Local project path")
    profile_name: Optional[str] = Field(
        None, description="dbt profile name to override the one in dbt_project.yml"
    )
    branch: Optional[str] = Field(None, description="Git branch")
    target: str = Field(Defaults.DBT_TARGET, description="dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description="dbt vars")
    compile: bool = Field(Defaults.DBT_COMPILE, description="Whether to compile")
    profiles_dir: Optional[str] = Field(
        None,
        description="Optional path to a dbt profiles directory or profiles.yml. Copied into the cloned project root before running dbt.",
    )

    connector_class: ClassVar[Type[DataConnector]] = DBTDatabricksConnector

    model_config = ConfigDict(extra="forbid")

    def get_citation_entries(
        self, mode: str = "model", include_query_text: bool = False
    ) -> list[CitationEntry]:
        provider_name = "databricks_dbt"
        try:
            manifest = DBTManifestConnector(
                package_url=self.package_url,
                project_dir=self.project_dir,
                profile_name=self.profile_name,
                branch=self.branch,
                target=self.target,
                vars=self.vars,
                profiles_dir=self.profiles_dir,
                compile=self.compile,
            )
            model_info = manifest.get_compiled_model_info(
                self.model_alias,
                model_unique_id=self.model_unique_id,
                model_package_name=self.model_package_name,
                model_selector_name=self.model_selector_name,
            )
        except Exception as error:
            logger.warning(
                "Failed to build dbt citation metadata for source '%s': %s",
                self.name,
                error,
            )
            model_info = None

        return _build_dbt_citation_entries(
            source_name=self.name,
            provider=provider_name,
            mode=mode,
            model_info=model_info,
            execution_metadata={"warehouse": "databricks", "target": self.target},
            include_query_text=include_query_text,
        )


class DBTProjectConfig(BaseModel):
    """Composable DBT project settings shared across warehouse backends."""

    package_url: str = Field(..., description="Git URL of dbt project")
    project_dir: str = Field(..., description="Local project path")
    profile_name: Optional[str] = Field(
        None, description="dbt profile name to override the one in dbt_project.yml"
    )
    branch: Optional[str] = Field(None, description="Git branch")
    target: str = Field(Defaults.DBT_TARGET, description="dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description="dbt vars")
    compile: bool = Field(Defaults.DBT_COMPILE, description="Whether to compile")
    profiles_dir: Optional[str] = Field(
        None,
        description="Optional path to a dbt profiles directory or profiles.yml. Copied into the cloned project root before running dbt.",
    )

    model_config = ConfigDict(extra="forbid")


class DBTWarehouseConfig(BaseModel):
    """Warehouse execution backend for composable DBT sources."""

    type: Literal["databricks", "bigquery", "duckdb", "redshift"] = Field(
        "databricks", description="Warehouse backend type"
    )
    project_id: Optional[str] = Field(
        None,
        description=(
            "BigQuery project id override. Used when warehouse.type is "
            "'bigquery'; falls back to BIGQUERY_PROJECT/GOOGLE_CLOUD_PROJECT."
        ),
    )
    location: Optional[str] = Field(
        None,
        description=(
            "Warehouse location/region. For BigQuery this maps to query job "
            "location and optional client default location."
        ),
    )
    credentials_json: Optional[str] = Field(
        None,
        description=(
            "Optional BigQuery service account JSON payload string. Used only "
            "when warehouse.type is 'bigquery'."
        ),
    )
    credentials_path: Optional[str] = Field(
        None,
        description=(
            "Optional path to BigQuery service account JSON file. Used only "
            "when warehouse.type is 'bigquery'."
        ),
    )
    database: Optional[str] = Field(
        None,
        description=(
            "DuckDB database path (or ':memory:'). Required when "
            "warehouse.type is 'duckdb'."
        ),
    )
    read_only: bool = Field(
        True,
        description="Open DuckDB connection in read-only mode when using duckdb.",
    )
    file_search_path: Optional[str | list[str]] = Field(
        None,
        description=(
            "Optional DuckDB file_search_path setting for resolving relative files "
            "when warehouse.type is 'duckdb'."
        ),
    )
    host: Optional[str] = Field(
        None, description="Redshift host. Used when warehouse.type is 'redshift'."
    )
    port: Optional[int] = Field(
        None,
        ge=1,
        le=65535,
        description="Redshift port. Defaults to 5439 when omitted.",
    )
    user: Optional[str] = Field(
        None, description="Redshift database user for non-IAM auth."
    )
    password: Optional[str] = Field(
        None, description="Redshift database password for non-IAM auth."
    )
    iam: Optional[bool] = Field(None, description="Use Redshift IAM authentication.")
    db_user: Optional[str] = Field(None, description="Redshift IAM db_user override.")
    cluster_identifier: Optional[str] = Field(
        None, description="Redshift cluster identifier for IAM auth."
    )
    region: Optional[str] = Field(None, description="AWS region for Redshift IAM.")
    profile: Optional[str] = Field(None, description="AWS profile for Redshift IAM.")
    access_key_id: Optional[str] = Field(
        None, description="AWS access key id for Redshift IAM."
    )
    secret_access_key: Optional[str] = Field(
        None, description="AWS secret access key for Redshift IAM."
    )
    session_token: Optional[str] = Field(
        None, description="AWS session token for Redshift IAM."
    )
    is_serverless: Optional[bool] = Field(
        None, description="Use Redshift Serverless endpoint resolution."
    )
    serverless_acct_id: Optional[str] = Field(
        None, description="Redshift Serverless account id."
    )
    serverless_work_group: Optional[str] = Field(
        None, description="Redshift Serverless workgroup."
    )
    ssl: Optional[bool] = Field(
        None, description="Enable Redshift SSL; defaults to true when omitted."
    )
    sslmode: Optional[str] = Field(None, description="Redshift SSL mode.")
    timeout: Optional[int] = Field(
        None,
        gt=0,
        description=(
            "Warehouse timeout seconds. For BigQuery this bounds query and "
            "result waits; for Redshift this controls connection timeout."
        ),
    )
    application_name: Optional[str] = Field(
        None, description="Redshift application_name; defaults to Slideflow."
    )
    connection_options: dict[str, Any] = Field(
        default_factory=dict,
        description="Advanced redshift_connector.connect options.",
    )

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_duckdb_required_fields(self):
        if self.type == "duckdb" and not self.database:
            raise ValueError(
                "warehouse.database is required when warehouse.type is 'duckdb'."
            )
        return self


class DBTSourceConfig(BaseSourceConfig):
    """Composable DBT source configuration with explicit dbt + warehouse blocks.

    This additive format is intended for future multi-warehouse DBT support while
    preserving legacy ``type: databricks_dbt`` behavior.
    """

    type: Literal["dbt"] = Field("dbt", description="Composable dbt data source")
    model_alias: str = Field(..., description="dbt model alias")
    model_unique_id: Optional[str] = Field(
        None, description="Optional dbt unique_id selector for alias disambiguation"
    )
    model_package_name: Optional[str] = Field(
        None, description="Optional dbt package_name selector for alias disambiguation"
    )
    model_selector_name: Optional[str] = Field(
        None, description="Optional dbt model name selector for alias disambiguation"
    )
    dbt: DBTProjectConfig = Field(..., description="DBT project settings")
    warehouse: DBTWarehouseConfig = Field(..., description="Warehouse backend settings")

    # BaseSourceConfig expects a connector_class; get_connector handles
    # warehouse-specific routing for composable dbt sources.
    connector_class: ClassVar[Type[DataConnector]] = DBTDatabricksConnector

    model_config = ConfigDict(extra="forbid")

    def get_connector(self) -> DataConnector:
        """Resolve composable DBT config to a concrete connector."""
        if self.warehouse.type == "databricks":
            return self._configure_connector(
                DBTDatabricksConnector(
                    model_alias=self.model_alias,
                    model_unique_id=self.model_unique_id,
                    model_package_name=self.model_package_name,
                    model_selector_name=self.model_selector_name,
                    package_url=self.dbt.package_url,
                    project_dir=self.dbt.project_dir,
                    profile_name=self.dbt.profile_name,
                    branch=self.dbt.branch,
                    target=self.dbt.target,
                    vars=self.dbt.vars,
                    compile=self.dbt.compile,
                    profiles_dir=self.dbt.profiles_dir,
                )
            )
        if self.warehouse.type == "bigquery":
            return self._configure_connector(
                DBTBigQueryConnector(
                    model_alias=self.model_alias,
                    model_unique_id=self.model_unique_id,
                    model_package_name=self.model_package_name,
                    model_selector_name=self.model_selector_name,
                    package_url=self.dbt.package_url,
                    project_dir=self.dbt.project_dir,
                    profile_name=self.dbt.profile_name,
                    branch=self.dbt.branch,
                    target=self.dbt.target,
                    vars=self.dbt.vars,
                    compile=self.dbt.compile,
                    profiles_dir=self.dbt.profiles_dir,
                    project_id=self.warehouse.project_id,
                    location=self.warehouse.location,
                    credentials_json=self.warehouse.credentials_json,
                    credentials_path=self.warehouse.credentials_path,
                    timeout=self.warehouse.timeout,
                )
            )
        if self.warehouse.type == "duckdb":
            return self._configure_connector(
                DBTDuckDBConnector(
                    model_alias=self.model_alias,
                    model_unique_id=self.model_unique_id,
                    model_package_name=self.model_package_name,
                    model_selector_name=self.model_selector_name,
                    package_url=self.dbt.package_url,
                    project_dir=self.dbt.project_dir,
                    profile_name=self.dbt.profile_name,
                    branch=self.dbt.branch,
                    target=self.dbt.target,
                    vars=self.dbt.vars,
                    compile=self.dbt.compile,
                    profiles_dir=self.dbt.profiles_dir,
                    database=self.warehouse.database or ":memory:",
                    read_only=self.warehouse.read_only,
                    file_search_path=self.warehouse.file_search_path,
                )
            )
        if self.warehouse.type == "redshift":
            return self._configure_connector(
                DBTRedshiftConnector(
                    model_alias=self.model_alias,
                    model_unique_id=self.model_unique_id,
                    model_package_name=self.model_package_name,
                    model_selector_name=self.model_selector_name,
                    package_url=self.dbt.package_url,
                    project_dir=self.dbt.project_dir,
                    profile_name=self.dbt.profile_name,
                    branch=self.dbt.branch,
                    target=self.dbt.target,
                    vars=self.dbt.vars,
                    compile=self.dbt.compile,
                    profiles_dir=self.dbt.profiles_dir,
                    host=self.warehouse.host,
                    port=self.warehouse.port,
                    database=self.warehouse.database,
                    user=self.warehouse.user,
                    password=self.warehouse.password,
                    iam=self.warehouse.iam,
                    db_user=self.warehouse.db_user,
                    cluster_identifier=self.warehouse.cluster_identifier,
                    region=self.warehouse.region,
                    profile=self.warehouse.profile,
                    access_key_id=self.warehouse.access_key_id,
                    secret_access_key=self.warehouse.secret_access_key,
                    session_token=self.warehouse.session_token,
                    is_serverless=self.warehouse.is_serverless,
                    serverless_acct_id=self.warehouse.serverless_acct_id,
                    serverless_work_group=self.warehouse.serverless_work_group,
                    ssl=self.warehouse.ssl,
                    sslmode=self.warehouse.sslmode,
                    timeout=self.warehouse.timeout,
                    application_name=self.warehouse.application_name,
                    connection_options=self.warehouse.connection_options,
                )
            )
        raise DataSourceError(f"Unsupported DBT warehouse type '{self.warehouse.type}'")

    def get_citation_entries(
        self, mode: str = "model", include_query_text: bool = False
    ) -> list[CitationEntry]:
        provider_name = f"{self.warehouse.type}_dbt"
        try:
            manifest = DBTManifestConnector(
                package_url=self.dbt.package_url,
                project_dir=self.dbt.project_dir,
                profile_name=self.dbt.profile_name,
                branch=self.dbt.branch,
                target=self.dbt.target,
                vars=self.dbt.vars,
                profiles_dir=self.dbt.profiles_dir,
                compile=self.dbt.compile,
            )
            model_info = manifest.get_compiled_model_info(
                self.model_alias,
                model_unique_id=self.model_unique_id,
                model_package_name=self.model_package_name,
                model_selector_name=self.model_selector_name,
            )
        except Exception as error:
            logger.warning(
                "Failed to build dbt citation metadata for source '%s': %s",
                self.name,
                error,
            )
            model_info = None

        return _build_dbt_citation_entries(
            source_name=self.name,
            provider=provider_name,
            mode=mode,
            model_info=model_info,
            execution_metadata={
                "warehouse": self.warehouse.type,
                "target": self.dbt.target,
            },
            include_query_text=include_query_text,
        )


def prepare_dbt_sources(sources: Sequence[BaseSourceConfig]) -> None:
    """Batch-prepare dbt sources by normalized project identity."""
    groups: dict[
        tuple,
        tuple[
            DBTManifestConnector,
            list[tuple[str, Optional[str], Optional[str], Optional[str]]],
        ],
    ] = {}
    for source in sources:
        if getattr(source, "type", None) not in {"dbt", "databricks_dbt"}:
            continue
        connector = source.get_connector()
        if not isinstance(connector, _DBTWarehouseConnectorBase):
            continue
        manifest = (
            connector._manifest_connector or connector._create_manifest_connector()
        )
        key = _project_cache_key(
            manifest.package_url,
            manifest.project_dir,
            manifest.branch,
            manifest.target,
            manifest.vars,
            manifest.profiles_dir,
            manifest.profile_name,
        ) + (manifest.compile,)
        if key not in groups:
            groups[key] = (manifest, [])
        groups[key][1].append(
            (
                connector.model_alias,
                connector.model_unique_id,
                connector.model_package_name,
                connector.model_selector_name,
            )
        )

    for manifest, requests in groups.values():
        manifest.prepare_models(requests)
