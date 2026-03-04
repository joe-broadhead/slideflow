import pytest

import slideflow.ai.registry as ai_registry_module
from slideflow.utilities.exceptions import ProviderError


def test_ai_registry_custom_registration_and_factory_flow():
    class CustomProvider:
        def __init__(self, prefix=""):
            self.prefix = prefix

        def generate_text(self, prompt: str, **_kwargs) -> str:
            return f"{self.prefix}{prompt}"

    temp_name = "__phase3_custom_ai_provider__"

    ai_registry_module.register_provider(temp_name, CustomProvider)
    try:
        assert "openai" in ai_registry_module.list_available_providers()
        assert "databricks" in ai_registry_module.list_available_providers()
        assert "gemini" in ai_registry_module.list_available_providers()
        assert ai_registry_module.get_provider_class(temp_name) is CustomProvider

        instance = ai_registry_module.create_provider(temp_name, prefix=">")
        assert instance.generate_text("ok") == ">ok"
    finally:
        ai_registry_module.ai_provider_registry.remove(temp_name)


def test_ai_registry_missing_provider_errors():
    with pytest.raises(ProviderError, match="Unknown provider"):
        ai_registry_module.get_provider_class("__missing_provider__")

    with pytest.raises(ProviderError, match="Failed to create provider"):
        ai_registry_module.create_provider("__missing_provider__")
