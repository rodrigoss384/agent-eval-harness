"""Testes de configuração e resolução da factory de providers."""

import pytest

from src.config import PROVIDER_BASE_URLS, Settings
from src.llm.factory import ProviderNotConfiguredError, create_chat_model, resolve_role


def test_settings_normalizes_empty_role_values() -> None:
    settings = Settings(
        _env_file=None,
        eval_agent_provider="",  # type: ignore[arg-type]
        eval_agent_model="",
    )

    assert settings.eval_agent_provider is None
    assert settings.eval_agent_model is None


@pytest.mark.parametrize(
    ("provider", "key_field"),
    [
        ("openai", "openai_api_key"),
        ("gemini", "gemini_api_key"),
        ("openrouter", "openrouter_api_key"),
        ("opencode", "opencode_api_key"),
    ],
)
def test_provider_role_resolves_supported_provider(provider: str, key_field: str) -> None:
    settings = Settings(
        _env_file=None,
        eval_agent_provider=provider,
        eval_agent_model="modelo-de-teste",
        **{key_field: "segredo-de-teste"},
    )

    resolved = resolve_role(settings, "agent")

    assert resolved.provider == provider
    assert resolved.model == "modelo-de-teste"
    assert resolved.base_url == PROVIDER_BASE_URLS[provider]
    assert resolved.api_key.get_secret_value() == "segredo-de-teste"


def test_unconfigured_role_raises_clear_error() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ProviderNotConfiguredError, match="agent"):
        create_chat_model(settings, "agent")
