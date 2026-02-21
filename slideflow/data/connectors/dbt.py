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
from pathlib import Path
from typing import Any, ClassVar, Iterator, Literal, Optional, Type

import pandas as pd
from dbt.cli.main import dbtRunner
from git import Repo
from pydantic import BaseModel, ConfigDict, Field

from slideflow.constants import Defaults
from slideflow.data.connectors.base import BaseSourceConfig, DataConnector
from slideflow.data.connectors.databricks import DatabricksConnector
from slideflow.utilities.exceptions import DataSourceError
from slideflow.utilities.logging import get_logger, log_data_operation, log_performance

logger = get_logger(__name__)

# Global cache for compiled DBT projects
_compiled_projects_cache: dict[tuple, Path] = {}
_compiled_projects_last_access: dict[tuple, float] = {}
_compilation_inflight: dict[tuple, threading.Event] = {}
_compilation_failures: dict[tuple, str] = {}
_compiled_projects_in_use: dict[Path, int] = {}
_pending_cleanup_dirs: set[Path] = set()
_cache_lock = threading.Lock()


def _sanitize_git_url(git_url: str) -> str:
    """Redact embedded basic-auth credentials from Git URLs."""
    return re.sub(r"(https?://)([^/@]+)@", r"\1***@", git_url)


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
            Repo.clone_from(git_url, clone_dir, branch=branch)
        else:
            Repo.clone_from(git_url, clone_dir)
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


def _cleanup_managed_clone_dir(clone_dir: Path) -> None:
    """Best-effort removal of managed clone directories during cache eviction."""
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
    except Exception as error:
        logger.warning(
            "Failed to remove evicted DBT clone directory '%s': %s", clone_dir, error
        )


def _acquire_compiled_project_lease_locked(clone_dir: Path) -> None:
    """Mark a compiled clone directory as actively in use.

    Requires caller to hold _cache_lock.
    """
    _compiled_projects_in_use[clone_dir] = (
        _compiled_projects_in_use.get(clone_dir, 0) + 1
    )


def _collect_ready_cleanup_dirs_locked() -> list[Path]:
    """Collect pending cleanup directories that are safe to remove.

    Requires caller to hold _cache_lock.
    """
    cached_dirs = set(_compiled_projects_cache.values())
    ready: list[Path] = []
    for clone_dir in list(_pending_cleanup_dirs):
        if _compiled_projects_in_use.get(clone_dir, 0) > 0:
            continue
        if clone_dir in cached_dirs:
            continue
        _pending_cleanup_dirs.discard(clone_dir)
        ready.append(clone_dir)
    return ready


def _cleanup_ready_managed_clone_dirs() -> None:
    """Best-effort cleanup for pending evicted clone directories."""
    with _cache_lock:
        ready_dirs = _collect_ready_cleanup_dirs_locked()
    for directory in ready_dirs:
        _cleanup_managed_clone_dir(directory)


def _release_compiled_project_lease(clone_dir: Path) -> None:
    """Release a compiled project lease and cleanup any newly-safe evictions."""
    with _cache_lock:
        current = _compiled_projects_in_use.get(clone_dir, 0)
        if current <= 1:
            _compiled_projects_in_use.pop(clone_dir, None)
        else:
            _compiled_projects_in_use[clone_dir] = current - 1

        ready_dirs = _collect_ready_cleanup_dirs_locked()

    for directory in ready_dirs:
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
            clone_dir = _compiled_projects_cache.get(oldest_key)
            if clone_dir is None:
                continue
            if _compiled_projects_in_use.get(clone_dir, 0) > 0:
                continue

            _compiled_projects_cache.pop(oldest_key, None)
            _compiled_projects_last_access.pop(oldest_key, None)
            _pending_cleanup_dirs.add(clone_dir)
            evicted = True
            break

        if not evicted:
            # All cache entries are actively in use. Temporarily exceed max_entries.
            break


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
    """Build a deterministic identity key for managed DBT clone directories."""
    payload = {
        "package_url": package_url,
        "branch": branch or "default",
        "target": target or "",
        "vars": vars or {},
        "profiles_dir": profiles_dir or "",
        "profile_name": profile_name or "",
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8")
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
        target=target,
        vars=vars,
        profiles_dir=profiles_dir,
        profile_name=profile_name,
    )
    return managed_root / key


def _get_compiled_project(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
    acquire_lease: bool = False,
) -> Path:
    """Get or create a compiled DBT project with caching.

    Retrieves a compiled DBT project from cache if available, or compiles
    a new project by cloning the repository and running DBT compilation.
    Projects are cached by their unique parameter combination to avoid
    redundant compilation operations.

    The function is thread-safe and handles concurrent access to the
    compilation cache. It logs performance metrics for both dependency
    installation and compilation phases.

    Args:
        package_url: Git URL of the DBT project repository.
        project_dir: Local directory path for the cloned project.
        branch: Optional Git branch to checkout.
        target: DBT target environment (e.g., 'dev', 'prod').
        vars: Optional DBT variables dictionary.
        profiles_dir: Optional path to a dbt profiles directory or profiles.yml.
        profile_name: Optional dbt profile name to override the one in dbt_project.yml.

    Returns:
        Path to the compiled DBT project directory.

    Raises:
        DataSourceError: If Git cloning or DBT compilation fails.

    Example:
        >>> project_path = _get_compiled_project(
        ...     "https://github.com/company/dbt-project.git",
        ...     "/tmp/dbt_project",
        ...     "main",
        ...     "prod",
        ...     {"start_date": "2024-01-01"}
        ... )
    """
    canonical_profiles_dir = _canonical_profiles_dir(profiles_dir)
    canonical_project_dir = _canonical_project_dir(project_dir)
    cache_key = (
        package_url,
        canonical_project_dir,
        branch,
        target,
        json.dumps(vars or {}, sort_keys=True),
        canonical_profiles_dir,
        profile_name,
    )

    max_cache_entries = _resolve_dbt_cache_max_entries()

    while True:
        with _cache_lock:
            cached_dir = _compiled_projects_cache.get(cache_key)
            if cached_dir is not None:
                if cached_dir.exists():
                    _compiled_projects_last_access[cache_key] = time.time()
                    if acquire_lease:
                        _acquire_compiled_project_lease_locked(cached_dir)
                    return cached_dir
                _compiled_projects_cache.pop(cache_key, None)
                _compiled_projects_last_access.pop(cache_key, None)

            failure_message = _compilation_failures.get(cache_key)
            if failure_message is not None:
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

        try:
            clone_dir = _resolve_managed_clone_dir(
                project_dir=canonical_project_dir,
                package_url=package_url,
                branch=branch,
                target=target,
                vars=vars,
                profiles_dir=canonical_profiles_dir,
                profile_name=profile_name,
            )
            with _cache_lock:
                _pending_cleanup_dirs.discard(clone_dir)
            _clone_repo(package_url, clone_dir, branch)

            # If provided, copy profiles directory or file into cloned project root
            if profiles_dir:
                try:
                    src = Path(profiles_dir)
                    if src.is_dir():
                        # Prefer a direct profiles.yml in the given directory
                        candidate = src / "profiles.yml"
                        if candidate.exists():
                            shutil.copy2(candidate, clone_dir / "profiles.yml")
                        else:
                            # Fallback: copy all yml/yaml files from directory
                            for p in src.glob("*.y*ml"):
                                shutil.copy2(p, clone_dir / p.name)
                    elif src.is_file():
                        # If a file is passed, copy to profiles.yml in clone_dir
                        dest = clone_dir / (
                            "profiles.yml" if src.name != "profiles.yml" else src.name
                        )
                        shutil.copy2(src, dest)
                    else:
                        logger.warning(f"profiles_dir path not found: {profiles_dir}")
                except Exception as e:
                    logger.warning(
                        f"Failed to prepare dbt profiles from {profiles_dir}: {e}"
                    )

            runner = dbtRunner()
            project_profiles_path = clone_dir / "profiles.yml"
            use_project_profiles_dir = (
                bool(profiles_dir) or project_profiles_path.exists()
            )

            # Log dependencies install
            deps_start = time.time()
            deps_args = ["deps", "--project-dir", str(clone_dir)]
            if profile_name:
                deps_args.extend(["--profile", profile_name])
            if use_project_profiles_dir:
                deps_args.extend(["--profiles-dir", str(clone_dir)])
            deps_result = runner.invoke(deps_args)
            _ensure_dbt_invoke_success("deps", deps_result)
            deps_duration = time.time() - deps_start
            log_performance(
                "dbt_deps", deps_duration, project=package_url, target=target
            )

            # Log compilation
            compile_start = time.time()
            args = ["compile", "--project-dir", str(clone_dir), "--target", target]
            if use_project_profiles_dir:
                args.extend(["--profiles-dir", str(clone_dir)])
            if profile_name:
                args.extend(["--profile", profile_name])
            if vars:
                args += ["--vars", json.dumps(vars)]
            compile_result = runner.invoke(args)
            _ensure_dbt_invoke_success("compile", compile_result)
            compile_duration = time.time() - compile_start
            log_performance(
                "dbt_compile",
                compile_duration,
                project=package_url,
                target=target,
                vars_count=len(vars) if vars else 0,
            )
        except BaseException as error:
            failure_message = str(error) or type(error).__name__
            with _cache_lock:
                _compilation_failures[cache_key] = failure_message
                event = _compilation_inflight.pop(cache_key, None)
                if event is not None:
                    event.set()
            raise

        with _cache_lock:
            _compiled_projects_cache[cache_key] = clone_dir
            _compiled_projects_last_access[cache_key] = time.time()
            _compilation_failures.pop(cache_key, None)
            _prune_compiled_projects_cache_locked(max_cache_entries)
            if acquire_lease:
                _acquire_compiled_project_lease_locked(clone_dir)
            event = _compilation_inflight.pop(cache_key, None)
            if event is not None:
                event.set()
        _cleanup_ready_managed_clone_dirs()

        return clone_dir


@contextmanager
def _compiled_project_lease(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str] = None,
    profile_name: Optional[str] = None,
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
        acquire_lease=True,
    )
    try:
        yield clone_dir
    finally:
        _release_compiled_project_lease(clone_dir)


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

    def get_compiled_query(self, model_name: str) -> Optional[str]:
        """Extract compiled SQL query for a specific DBT model.

        Compiles the DBT project if needed and parses the manifest.json file
        to find the compiled SQL for the specified model alias. Returns the
        SQL content as a string for execution by other connectors.

        Args:
            model_name: The alias of the DBT model to retrieve SQL for.
                This should match the alias defined in the model's configuration.

        Returns:
            The compiled SQL query as a string, or None if the model is not found.

        Raises:
            DataSourceError: If the manifest.json file is not found or invalid.

        Example:
            >>> connector = DBTManifestConnector(
            ...     package_url="https://github.com/company/dbt-project.git",
            ...     project_dir="/tmp/dbt_project",
            ...     target="prod"
            ... )
            >>> sql = connector.get_compiled_query("monthly_revenue")
            >>> print(f"Found SQL query with {len(sql)} characters")
        """
        with _compiled_project_lease(
            package_url=self.package_url,
            project_dir=self.project_dir,
            branch=self.branch,
            target=self.target,
            vars=self.vars,
            profiles_dir=self.profiles_dir,
            profile_name=self.profile_name,
        ) as clone_dir:
            # Load manifest.json
            manifest_path = clone_dir / "target" / "manifest.json"
            if not manifest_path.exists():
                raise DataSourceError(f"manifest.json not found at {manifest_path}")

            with open(manifest_path) as f:
                manifest = json.load(f)

            # Find the compiled SQL for the model
            for node in manifest.get("nodes", {}).values():
                if node.get("resource_type") not in ("model", "analysis"):
                    continue
                alias = node.get("alias")
                if alias == model_name:
                    path = node.get("compiled_path")
                    full = clone_dir / path if path else None
                    if full and full.exists():
                        return full.read_text()
                    else:
                        logger.warning(f"Missing compiled file for {alias}: {path}")

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


class DBTDatabricksConnector(BaseModel, DataConnector):
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

    model_alias: str
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

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._manifest_connector = DBTManifestConnector(
            package_url=self.package_url,
            project_dir=self.project_dir,
            branch=self.branch,
            target=self.target,
            vars=self.vars,
            profiles_dir=self.profiles_dir,
            compile=self.compile,
            profile_name=self.profile_name,
        )

    def fetch_data(self) -> pd.DataFrame:
        """Compile DBT model and execute against Databricks.

        Extracts the compiled SQL from the DBT model and executes it
        against the configured Databricks SQL warehouse. Returns the
        query results as a pandas DataFrame.

        Returns:
            DataFrame containing the results of the compiled DBT model query.

        Raises:
            DataSourceError: If the specified model is not found or compilation fails.
            ConnectionError: If unable to connect to Databricks.
            sql.Error: If the compiled SQL query execution fails.

        Example:
            >>> connector = DBTDatabricksConnector(
            ...     model_alias="revenue_summary",
            ...     package_url="https://github.com/company/dbt-project.git",
            ...     project_dir="/tmp/dbt_project"
            ... )
            >>> df = connector.fetch_data()
            >>> print(f"Model returned {len(df)} rows, {len(df.columns)} columns")
        """
        if self._manifest_connector is None:
            raise DataSourceError("DBT manifest connector is not initialized.")
        sql_text = self._manifest_connector.get_compiled_query(self.model_alias)
        if not sql_text:
            raise DataSourceError(f"No compiled model '{self.model_alias}'")
        return DatabricksConnector(sql_text).fetch_data()


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
