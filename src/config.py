"""Configuração centralizada e segura da aplicação."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["openai", "gemini", "openrouter", "opencode"]

PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
    "opencode": "https://opencode.ai/zen/v1",
}


class Settings(BaseSettings):
    """Variáveis de ambiente aceitas pelo harness."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_path: Path = Path("var/evals.db")
    static_dir: Path = Path("frontend/dist")

    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    opencode_api_key: SecretStr | None = None
    jev_api_key: SecretStr | None = None
    jev_base_url: str = "https://openrouter.ai/api/alpha/decisions"
    jev_model: str = "typesafe/jev-1.13"

    openai_base_url: str = PROVIDER_BASE_URLS["openai"]
    gemini_base_url: str = PROVIDER_BASE_URLS["gemini"]
    openrouter_base_url: str = PROVIDER_BASE_URLS["openrouter"]
    opencode_base_url: str = PROVIDER_BASE_URLS["opencode"]

    eval_agent_provider: ProviderName | None = None
    eval_agent_model: str | None = None
    eval_judge_provider: ProviderName | None = None
    eval_judge_model: str | None = None
    eval_judge_alt_provider: ProviderName | None = None
    eval_judge_alt_model: str | None = None
    llm_timeout_seconds: float = 60
    llm_max_concurrency: int = 4

    @field_validator(
        "eval_agent_provider",
        "eval_agent_model",
        "eval_judge_provider",
        "eval_judge_model",
        "eval_judge_alt_provider",
        "eval_judge_alt_model",
        mode="before",
    )
    @classmethod
    def empty_role_value_as_none(cls, value: object) -> object:
        """Trata campos vazios do arquivo .env como papel não configurado."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    def api_key_for(self, provider: str | None) -> SecretStr | None:
        """Retorna a chave do provider sem convertê-la para texto público."""
        if provider is None:
            return None
        return getattr(self, f"{provider}_api_key", None)

    def base_url_for(self, provider: str | None) -> str | None:
        """Resolve a URL configurada do provider informado."""
        if provider is None:
            return None
        return getattr(self, f"{provider}_base_url", None)
