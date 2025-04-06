from typing import Union, Dict, Any

from slideflow.data.connectors.common import DataConnector
from slideflow.data.connectors.csv import CSVConnector, CSVSourceConfig
from slideflow.data.connectors.databricks import DatabricksSQLConnector, DatabricksSourceConfig
from slideflow.data.connectors.dbt import DBTDatabricksConnector, DBTDatabricksSourceConfig, DBTManifestConnector

DataSourceConfig = Union[
    CSVSourceConfig,
    DatabricksSourceConfig,
    DBTDatabricksSourceConfig
]

CONNECTOR_FACTORY: Dict[str, Any] = {
    'csv': lambda config: CSVConnector(config.file_path),
    'databricks': lambda config: DatabricksSQLConnector(config.query),
    'databricks_dbt': lambda config: DBTDatabricksConnector(
        DBTManifestConnector(**config.dict(exclude = {'model_alias'})),
        config.model_alias
    )
}

def get_data_connector(data_source: DataSourceConfig) -> DataConnector:
    """
    Factory function to instantiate the appropriate data connector 
    for a given data source configuration.

    Looks up the connector type in the `CONNECTOR_FACTORY` registry and
    returns an instance of the matching connector class.

    Args:
        data_source (DataSourceConfig): The data source configuration object 
        containing type and connection parameters.

    Returns:
        DataConnector: An instance of the appropriate connector class.

    Raises:
        ValueError: If the `data_source.type` is not supported or not registered 
        in `CONNECTOR_FACTORY`.
    """
    connector_type = data_source.type
    factory = CONNECTOR_FACTORY.get(connector_type)
    if not factory:
        raise ValueError(f'Unsupported data_source type: {connector_type}')
    return factory(data_source)
