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

import os
import time
import json
import shutil
import threading
import pandas as pd
from git import Repo
from pathlib import Path
from dbt.cli.main import dbtRunner
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Literal, ClassVar, Type

from slideflow.constants import Defaults
from slideflow.utilities.exceptions import DataSourceError
from slideflow.data.connectors.databricks import DatabricksConnector
from slideflow.data.connectors.base import DataConnector, BaseSourceConfig
from slideflow.utilities.logging import get_logger, log_data_operation, log_performance

logger = get_logger(__name__)

# Global cache for compiled DBT projects
_compiled_projects_cache: dict[tuple, Path] = {}
_cache_lock = threading.Lock()

def _clone_repo(git_url: str, clone_dir: Path, branch: Optional[str]) -> None:
    """Clone a Git repository for DBT project access.
    
    Clones the specified Git repository to a local directory, optionally
    checking out a specific branch. Removes any existing directory at the
    target location before cloning.
    
    Args:
        git_url: Git repository URL to clone.
        clone_dir: Local directory path where the repository will be cloned.
        branch: Optional branch name to checkout. If None, uses default branch.
        
    Raises:
        DataSourceError: If the Git operation fails.
        
    Example:
        >>> _clone_repo(
        ...     "https://github.com/company/dbt-project.git",
        ...     Path("/tmp/dbt_project"),
        ...     "main"
        ... )
    """
    start_time = time.time()
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
    kwargs = {"branch": branch} if branch else {}
    try:
        Repo.clone_from(git_url, clone_dir, **kwargs)
        duration = time.time() - start_time
        log_data_operation("clone", "dbt_project", context = {
            "git_url": git_url, "branch": branch or "default", 
            "target_dir": str(clone_dir), "duration_seconds": duration
        })
    except Exception as e:
        duration = time.time() - start_time
        log_data_operation("clone", "dbt_project", context = {
            "git_url": git_url, "error": str(e), "duration_seconds": duration
        })
        raise DataSourceError(f"Error cloning {git_url}: {e}")

def _get_compiled_project(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]],
    profiles_dir: Optional[str] = None,
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
    cache_key = (
        package_url,
        project_dir,
        branch,
        target,
        json.dumps(vars or {}, sort_keys = True),
        str(Path(profiles_dir).resolve()) if profiles_dir else None,
    )
    
    with _cache_lock:
        if cache_key in _compiled_projects_cache:
            cached_dir = _compiled_projects_cache[cache_key]
            if cached_dir.exists():
                return cached_dir
        
        # Compile the project
        clone_dir = Path(project_dir)
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
                    dest = clone_dir / ("profiles.yml" if src.name != "profiles.yml" else src.name)
                    shutil.copy2(src, dest)
                else:
                    logger.warning(f"profiles_dir path not found: {profiles_dir}")
            except Exception as e:
                logger.warning(f"Failed to prepare dbt profiles from {profiles_dir}: {e}")

        cwd = Path.cwd()
        os.chdir(clone_dir)
        
        try:
            runner = dbtRunner()
            
            # Log dependencies install
            deps_start = time.time()
            runner.invoke(["deps"])
            deps_duration = time.time() - deps_start
            log_performance("dbt_deps", deps_duration, project = package_url, target = target)
            
            # Log compilation
            compile_start = time.time()
            args = ["compile", "--profiles-dir", str(clone_dir), "--target", target]
            if vars:
                args += ["--vars", json.dumps(vars)]
            runner.invoke(args)
            compile_duration = time.time() - compile_start
            log_performance(
                "dbt_compile",
                compile_duration,
                project = package_url,
                target = target, 
                vars_count = len(vars) if vars else 0
            )
        finally:
            os.chdir(cwd)
        
        _compiled_projects_cache[cache_key] = clone_dir
        return clone_dir

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
    package_url: str = Field(..., description = "Git URL of dbt project")
    project_dir: str = Field(..., description = "Local path to dbt project")
    branch: Optional[str] = Field(None, description = "Git branch to checkout")
    target: str = Field(Defaults.DBT_TARGET, description = "dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description = "dbt vars")
    profiles_dir: Optional[str] = Field(
        None,
        description = "Optional path to a dbt profiles directory or profiles.yml to use. If provided, it will be copied into the cloned project directory before running dbt.",
    )
    compile: bool = Field(Defaults.DBT_COMPILE, description = "Whether to compile project")

    model_config = ConfigDict(arbitrary_types_allowed = True, extra = "forbid")

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
        clone_dir = _get_compiled_project(
            self.package_url, 
            self.project_dir, 
            self.branch, 
            self.target, 
            self.vars,
            self.profiles_dir,
        )
        
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
        raise NotImplementedError("DBTManifestConnector is for manifest parsing, not data fetching. Use get_compiled_query() instead.")

class DBTDatabricksConnector(DataConnector):
    """Connector that combines DBT model compilation with Databricks execution.
    
    This connector bridges DBT transformations with Databricks SQL execution.
    It compiles DBT models to SQL and executes them against Databricks SQL
    warehouses, providing a complete data transformation and retrieval pipeline.
    
    The connector handles the full workflow:
    1. Compile the DBT project and extract model SQL
    2. Execute the compiled SQL against Databricks
    3. Return results as a pandas DataFrame
    
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
    def __init__(
        self,
        model_alias: str,
        package_url: str,
        project_dir: str,
        branch: Optional[str] = None,
        target: str = Defaults.DBT_TARGET,
        vars: Optional[dict[str, Any]] = None,
        compile: bool = Defaults.DBT_COMPILE,
        profiles_dir: Optional[str] = None,
    ) -> None:
        """Initialize the DBT-Databricks connector.
        
        Args:
            model_alias: The alias of the DBT model to execute.
            package_url: Git URL of the DBT project repository.
            project_dir: Local directory path for cloning the project.
            branch: Optional Git branch to checkout.
            target: DBT target environment for compilation.
            vars: Optional variables to pass to DBT compilation.
            compile: Whether to compile the project.
            profiles_dir: Optional path to dbt profiles directory/file to copy into the project.
        """
        self.model_alias = model_alias
        self._manifest_connector = DBTManifestConnector(
            package_url = package_url,
            project_dir = project_dir,
            branch = branch,
            target = target,
            vars = vars,
            profiles_dir = profiles_dir,
            compile = compile,
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
        >>> config = DBTDatabricksSourceConfig(**config_dict)
    """
    type: Literal["databricks_dbt"] = Field("databricks_dbt", description = "dbt + Databricks data source")
    model_alias: str = Field(..., description = "dbt model alias")
    package_url: str = Field(..., description = "Git URL of dbt project")
    project_dir: str = Field(..., description = "Local project path")
    branch: Optional[str] = Field(None, description = "Git branch")
    target: str = Field(Defaults.DBT_TARGET, description = "dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description = "dbt vars")
    compile: bool = Field(Defaults.DBT_COMPILE, description = "Whether to compile")
    profiles_dir: Optional[str] = Field(
        None,
        description = "Optional path to a dbt profiles directory or profiles.yml. Copied into the cloned project root before running dbt.",
    )

    connector_class: ClassVar[Type[DataConnector]] = DBTDatabricksConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type"
    )
