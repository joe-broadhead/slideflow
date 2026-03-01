"""Factory and registry for workbook providers."""

from typing import Type

from slideflow.core.registry import create_class_registry
from slideflow.utilities.exceptions import ConfigurationError
from slideflow.workbooks.config import WorkbookProviderConfig as WorkbookProviderSpec
from slideflow.workbooks.providers.base import WorkbookProvider, WorkbookProviderConfig
from slideflow.workbooks.providers.google_sheets import (
    GoogleSheetsProvider,
    GoogleSheetsProviderConfig,
)

provider_registry = create_class_registry("workbook_providers", WorkbookProvider)
config_registry = create_class_registry(
    "workbook_provider_configs", WorkbookProviderConfig
)

provider_registry.register_class("google_sheets", GoogleSheetsProvider)
config_registry.register_class("google_sheets", GoogleSheetsProviderConfig)


class WorkbookProviderFactory:
    """Factory for creating workbook providers from config payloads."""

    @classmethod
    def register_provider(
        cls,
        provider_type: str,
        provider_class: Type[WorkbookProvider],
        config_class: Type[WorkbookProviderConfig],
    ) -> None:
        provider_registry.register_class(provider_type, provider_class, overwrite=True)
        config_registry.register_class(provider_type, config_class, overwrite=True)

    @classmethod
    def create_provider(cls, config: WorkbookProviderSpec) -> WorkbookProvider:
        provider_type = config.type
        if not provider_registry.has(provider_type):
            available = provider_registry.list_available()
            raise ConfigurationError(
                f"Unsupported workbook provider type '{provider_type}'. "
                f"Available providers: {available}"
            )

        provider_class = provider_registry.get_class(provider_type)
        config_class = config_registry.get_class(provider_type)
        provider_config = config_class(**config.config)
        return provider_class(provider_config)
