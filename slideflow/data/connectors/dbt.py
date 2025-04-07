import os
import git
import json
import shutil
import logging
from git import Repo
import pandas as pd
from pathlib import Path
from pydantic import BaseModel
from dbt.cli.main import dbtRunner
from pydantic import Field, model_validator, PrivateAttr
from typing import Annotated, Literal, Optional, Any, Dict

from slideflow.data.connectors.databricks import DatabricksSQLConnector
from slideflow.data.connectors.common import DataConnector, BaseSourceConfig

logger = logging.getLogger(__name__)

def clone_dbt_package(git_url: str, clone_dir: str) -> Repo:
    """
    Clones a Git repository containing a dbt project to a specified local directory.

    If the target directory already exists, it will be removed before cloning.

    Args:
        git_url (str): The URL of the Git repository to clone.
        clone_dir (str): The local directory where the repository should be cloned.

    Returns:
        Repo: A GitPython `Repo` object representing the cloned repository.

    Raises:
        RuntimeError: If the clone operation fails due to a Git or filesystem error.
    """
    if os.path.exists(clone_dir):
        shutil.rmtree(clone_dir)
    try:
        repo = Repo.clone_from(git_url, clone_dir)
        logger.info(f'Cloned dbt project from {git_url} to {clone_dir}')
        return repo
    except git.exc.GitCommandError as e:
        raise RuntimeError(f'Git error cloning repository: {e}')
    except OSError as e:
        raise RuntimeError(f'Filesystem error during clone: {e}')

class DBTManifestConnector(BaseModel):
    """
    Configuration for loading and compiling a dbt project from a GitHub repository.

    This model encapsulates the information required to clone a dbt project, compile it, and
    optionally load its manifest.json contents.

    Attributes:
        package_url (str): GitHub URL of the dbt project repository.
        project_dir (str): Path to the local directory where the dbt project will be cloned or stored.
        target (str): The dbt target environment to use (e.g., "prod", "dev"). Defaults to "prod".
        vars (Optional[Dict[str, Any]]): Optional dictionary of variables to pass to dbt when compiling.
        compile (bool): Whether to compile the dbt project after cloning. Defaults to True.
        manifest (Dict[str, Any]): Dictionary containing the contents of dbt's manifest.json file. Defaults to an empty dict.
    """
    package_url: Annotated[str, Field(description = 'GitHub URL of the dbt project.')]
    project_dir: Annotated[str, Field(description = 'Path to the local dbt project directory.')]
    target: Annotated[str, Field(default = 'prod', description = 'Target environment for dbt.')]
    vars: Annotated[Optional[Dict[str, Any]], Field(default = None, description = 'Optional dbt variables.')]
    compile: Annotated[bool, Field(default = True, description = 'Whether to compile the dbt project.')]
    manifest: Annotated[Dict[str, Any], Field(default_factory = dict, description = 'Loaded dbt manifest.json content.')]

    _compiled_models: Optional[Dict[str, str]] = PrivateAttr(default = None)

    @model_validator(mode = 'after')
    def load_manifest(self) -> 'DBTManifestConnector':
        """
        Compiles the dbt project and loads the `manifest.json` after model initialization.

        This validator performs the following:
        - Changes working directory to the specified dbt project directory.
        - Clones the dbt project from GitHub if compilation is enabled.
        - Runs `dbt deps` and `dbt compile` using the configured target and optional vars.
        - Loads the resulting `manifest.json` into the model.

        Raises:
            FileNotFoundError: If the `manifest.json` file is not found after compilation.
            RuntimeError: If the Git clone or dbt compilation fails.

        Returns:
            DBTManifestConnector: The instance with `manifest` field populated.
        """
        cli = dbtRunner()
        original_cwd = os.getcwd()

        if self.compile:
            clone_dbt_package(self.package_url, self.project_dir)

            os.chdir(self.project_dir)

            cli.invoke(['deps'])
            args = ['compile', '--profiles-dir', self.project_dir, '--target', self.target]
            if self.vars:
                args += ['--vars', json.dumps(self.vars)]
            cli.invoke(args)

        os.chdir(original_cwd)

        manifest_path = Path(self.project_dir) / 'target' / 'manifest.json'
        if not manifest_path.exists():
            raise FileNotFoundError('manifest.json not found in target directory.')
        with open(manifest_path, 'r') as f:
            self.manifest = json.load(f)
        return self

    def get_compiled_models(self) -> Dict[str, str]:
        """
        Loads compiled SQL models from the dbt manifest.

        This method reads the compiled SQL files for all `model` and `analysis` nodes
        listed in the `manifest.json`, returning a dictionary that maps model aliases
        to their compiled SQL content.

        If a compiled file is referenced in the manifest but not found on disk, a warning is logged.

        Returns:
            Dict[str, str]: A dictionary where keys are model aliases and values are compiled SQL strings.
        """
        if self._compiled_models is not None:
            return self._compiled_models
        
        models = {}
        compiled_dir = Path(self.project_dir) / 'target' / 'compiled'
        if not compiled_dir.exists():
            logger.warning('⚠️  Compiled directory not found!')
            return models

        for node in self.manifest.get('nodes', {}).values():
            if node.get('resource_type') not in ['model', 'analysis']:
                continue
            model_alias = node.get('alias')
            compiled_path = node.get('compiled_path')
            if compiled_path:
                full_path = Path(self.project_dir) / compiled_path
                if full_path.exists():
                    models[model_alias] = full_path.read_text()
                else:
                    logger.error(f'Compiled file not found for: {model_alias} at {compiled_path}')
        
        self._compiled_models = models
        return models

    def get_compiled_query(self, model_name: str) -> Optional[str]:
        """
        Retrieves the compiled SQL for a given dbt model alias.

        This method looks up the compiled SQL for the specified model name
        (i.e., the alias defined in the dbt project) by scanning the compiled models.

        Args:
            model_name (str): The alias of the dbt model to retrieve.

        Returns:
            Optional[str]: The compiled SQL string if found, otherwise None.
        """
        return self.get_compiled_models().get(model_name)

class DBTDatabricksConnector(DataConnector):
    """
    Connector that fetches data by executing a compiled dbt model query on Databricks.

    This connector uses a pre-loaded DBTManifestConnector to retrieve the compiled
    SQL for a given model alias, and then runs it against a Databricks SQL endpoint.

    Args:
        manifest_connector (DBTManifestConnector): The manifest loader containing compiled dbt models.
        model_alias (str): The alias of the dbt model to query.

    Raises:
        ValueError: If the compiled SQL for the model alias is not found.
    """
    def __init__(self, manifest_connector: DBTManifestConnector, model_alias: str):
        self.manifest_connector = manifest_connector
        self.model_alias = model_alias

    def fetch_data(self) -> pd.DataFrame:
        """
        Executes the compiled dbt model query on Databricks and returns the result.

        Returns:
            pd.DataFrame: The result of the query as a DataFrame.

        Raises:
            ValueError: If the model alias is not found in the manifest.
        """
        logger.info(f'Fetching data from DBT Databricks: {self.model_alias}')
        query = self.manifest_connector.get_compiled_query(self.model_alias)
        if not query:
            raise ValueError(f"Model alias '{self.model_alias}' not found in the DBT manifest.")
        return DatabricksSQLConnector(query).fetch_data()


class DBTDatabricksSourceConfig(BaseSourceConfig):
    """
    Configuration for a data source that fetches from a dbt model executed on Databricks.

    This config specifies how to locate and compile the dbt project, and which model to query.

    Attributes:
        type (Literal['databricks_dbt']): The type identifier for this data source.
        model_alias (str): The alias of the dbt model to execute.
        project_dir (str): Path to the local dbt project directory.
        target (Optional[str]): dbt target environment. Defaults to 'prod'.
        vars (Optional[Dict[str, Any]]): Optional variables to pass to dbt compilation.
        compile (Optional[bool]): Whether to compile the dbt project. Defaults to True.
    """
    type: Literal['databricks_dbt'] = Field('databricks_dbt', description = 'DBT + Databricks data source.')
    model_alias: Annotated[str, Field(description = 'Model alias to execute.')]
    package_url: Annotated[str, Field(description = 'GitHub URL of the dbt project.')]
    project_dir: Annotated[str, Field(description = 'Path to dbt project.')]
    target: Annotated[Optional[str], Field(default = 'prod', description = 'dbt target environment.')]
    vars: Annotated[Optional[Dict[str, Any]], Field(default = None, description = 'Optional dbt variables.')]
    compile: Annotated[Optional[bool], Field(default = True, description = 'Whether to compile the dbt project.')]
