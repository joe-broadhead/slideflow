import os
import json
import shutil
import threading
import time
import pandas as pd
from git import Repo
from pathlib import Path
from dbt.cli.main import dbtRunner
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Literal, ClassVar, Type

from slideflow.data.connectors.databricks import DatabricksConnector
from slideflow.data.connectors.base import DataConnector, BaseSourceConfig
from slideflow.constants import Defaults
from slideflow.utilities.exceptions import DataSourceError
from slideflow.utilities.logging import get_logger, log_data_operation, log_performance

logger = get_logger(__name__)

# Global cache for compiled DBT projects
_compiled_projects_cache: dict[tuple, Path] = {}
_cache_lock = threading.Lock()

def _clone_repo(git_url: str, clone_dir: Path, branch: Optional[str]) -> None:
    start_time = time.time()
    if clone_dir.exists():
        shutil.rmtree(clone_dir)
    kwargs = {"branch": branch} if branch else {}
    try:
        Repo.clone_from(git_url, clone_dir, **kwargs)
        duration = time.time() - start_time
        log_data_operation("clone", "dbt_project", context={
            "git_url": git_url, "branch": branch or "default", 
            "target_dir": str(clone_dir), "duration_seconds": duration
        })
    except Exception as e:
        duration = time.time() - start_time
        log_data_operation("clone", "dbt_project", context={
            "git_url": git_url, "error": str(e), "duration_seconds": duration
        })
        raise DataSourceError(f"Error cloning {git_url}: {e}")

def _get_compiled_project(
    package_url: str,
    project_dir: str,
    branch: Optional[str],
    target: str,
    vars: Optional[dict[str, Any]]
) -> Path:
    """Get or create a compiled DBT project, cached by unique parameters."""
    cache_key = (package_url, project_dir, branch, target, json.dumps(vars or {}, sort_keys=True))
    
    with _cache_lock:
        if cache_key in _compiled_projects_cache:
            cached_dir = _compiled_projects_cache[cache_key]
            if cached_dir.exists():
                return cached_dir
        
        # Compile the project
        clone_dir = Path(project_dir)
        _clone_repo(package_url, clone_dir, branch)
        
        cwd = Path.cwd()
        os.chdir(clone_dir)
        
        try:
            runner = dbtRunner()
            
            # Log dependencies install
            deps_start = time.time()
            runner.invoke(["deps"])
            deps_duration = time.time() - deps_start
            log_performance("dbt_deps", deps_duration, project=package_url, target=target)
            
            # Log compilation
            compile_start = time.time()
            args = ["compile", "--profiles-dir", str(clone_dir), "--target", target]
            if vars:
                args += ["--vars", json.dumps(vars)]
            runner.invoke(args)
            compile_duration = time.time() - compile_start
            log_performance("dbt_compile", compile_duration, project=package_url, target=target, 
                          vars_count=len(vars) if vars else 0)
        finally:
            os.chdir(cwd)
        
        _compiled_projects_cache[cache_key] = clone_dir
        return clone_dir

class DBTManifestConnector(BaseModel, DataConnector):
    package_url: str = Field(..., description="Git URL of dbt project")
    project_dir: str = Field(..., description="Local path to dbt project")
    branch: Optional[str]   = Field(None, description="Git branch to checkout")
    target: str             = Field(Defaults.DBT_TARGET, description="dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description="dbt vars")
    compile: bool           = Field(Defaults.DBT_COMPILE, description="Whether to compile project")

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    def get_compiled_query(self, model_name: str) -> Optional[str]:
        """
        Return the compiled SQL for a given model alias.
        """
        clone_dir = _get_compiled_project(
            self.package_url, 
            self.project_dir, 
            self.branch, 
            self.target, 
            self.vars
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
        """
        DBTManifestConnector doesn't fetch data directly - it provides compiled queries.
        This method is required by DataConnector but not applicable for manifest parsing.
        """
        raise NotImplementedError("DBTManifestConnector is for manifest parsing, not data fetching. Use get_compiled_query() instead.")

class DBTDatabricksConnector(DataConnector):
    def __init__(
        self,
        model_alias: str,
        package_url: str,
        project_dir: str,
        branch: Optional[str] = None,
        target: str = Defaults.DBT_TARGET,
        vars: Optional[dict[str, Any]] = None,
        compile: bool = Defaults.DBT_COMPILE,
    ) -> None:
        self.model_alias = model_alias
        self._manifest_connector = DBTManifestConnector(
            package_url=package_url,
            project_dir=project_dir,
            branch=branch,
            target=target,
            vars=vars,
            compile=compile
        )

    def fetch_data(self) -> pd.DataFrame:
        sql_text = self._manifest_connector.get_compiled_query(self.model_alias)
        if not sql_text:
            raise DataSourceError(f"No compiled model '{self.model_alias}'")
        return DatabricksConnector(sql_text).fetch_data()

class DBTDatabricksSourceConfig(BaseSourceConfig):
    """
    dbt-on-Databricks source config.
    """
    type: Literal["databricks_dbt"] = Field("databricks_dbt", description = "dbt + Databricks data source")
    model_alias: str = Field(..., description = "dbt model alias")
    package_url: str = Field(..., description = "Git URL of dbt project")
    project_dir: str = Field(..., description = "Local project path")
    branch: Optional[str] = Field(None, description = "Git branch")
    target: str = Field(Defaults.DBT_TARGET, description = "dbt target")
    vars: Optional[dict[str, Any]] = Field(None, description = "dbt vars")
    compile: bool = Field(Defaults.DBT_COMPILE, description = "Whether to compile")

    connector_class: ClassVar[Type[DataConnector]] = DBTDatabricksConnector

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type"
    )
