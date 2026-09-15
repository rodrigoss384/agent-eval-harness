"""Factory única e segura para os providers OpenAI-compatible."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.config import PROVIDER_BASE_URLS, ProviderName, Settings
from src.models import ToolCall, ToolSpec

ProviderRole = Literal["agent", "judge", "judge_alt"]


class ProviderConfigurationError(ValueError):
    """Erro legível de configuração de provider."""


class ProviderNotConfiguredError(ProviderConfigurationError):
    """Indica que um papel não possui provider, modelo ou chave completos."""


@dataclass(frozen=True, slots=True)
class ResolvedProvider:
    """Configuração privada resolvida para uma chamada LLM."""

    role: ProviderRole
    provider: ProviderName
    model: str
    base_url: str
    api_key: SecretStr


@dataclass(frozen=True, slots=True)
class RoleResponse:
    """Resposta mínima de uma chamada real, sem payload privado do provider."""

    text: str
    provider: ProviderName
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    time_to_first_token_ms: int | None = None
    finish_reason: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


_semaphores: dict[int, asyncio.Semaphore] = {}


def _semaphore(limit: int) -> asyncio.Semaphore:
    """Compartilha o limite de concorrência por processo."""
    if limit < 1:
        raise ProviderConfigurationError("LLM_MAX_CONCURRENCY deve ser maior que zero.")
    return _semaphores.setdefault(limit, asyncio.Semaphore(limit))


def resolve_role(settings: Settings, role: ProviderRole) -> ResolvedProvider:
    """Resolve provider, modelo, URL e segredo para um papel configurado."""
    provider = getattr(settings, f"eval_{role}_provider")
    model = getattr(settings, f"eval_{role}_model")
    if provider is None or not model:
        raise ProviderNotConfiguredError(
            f"O papel '{role}' exige EVAL_{role.upper()}_PROVIDER e EVAL_{role.upper()}_MODEL."
        )
    if provider not in PROVIDER_BASE_URLS:
        accepted = " | ".join(PROVIDER_BASE_URLS)
        raise ProviderConfigurationError(
            f"Provider '{provider}' inválido. Valores aceitos: {accepted}."
        )
    api_key = settings.api_key_for(provider)
    base_url = settings.base_url_for(provider)
    if api_key is None or not api_key.get_secret_value():
        raise ProviderNotConfiguredError(
            f"O papel '{role}' usa '{provider}', mas a chave correspondente não foi configurada."
        )
    if base_url is None:
        raise ProviderConfigurationError(f"Base URL ausente para o provider '{provider}'.")
    return ResolvedProvider(
        role=role,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )


def create_chat_model(settings: Settings, role: ProviderRole) -> ChatOpenAI:
    """Cria o adapter LangChain sem retry ou fallback automático."""
    resolved = resolve_role(settings, role)
    return ChatOpenAI(
        model=resolved.model,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
        stream_usage=True,
        temperature=0,
        max_completion_tokens=800,
    )


async def invoke_role(settings: Settings, role: ProviderRole, prompt: str) -> RoleResponse:
    """Executa uma chamada limitada pelo semáforo e captura usage disponível."""
    resolved = resolve_role(settings, role)
    model = create_chat_model(settings, role)
    started_at = perf_counter()
    async with _semaphore(settings.llm_max_concurrency):
        message = await model.ainvoke([HumanMessage(content=prompt)])
    latency_ms = round((perf_counter() - started_at) * 1000)
    usage = message.usage_metadata
    text = message.text if isinstance(message.text, str) else str(message.content)
    return RoleResponse(
        text=text,
        provider=resolved.provider,
        model=resolved.model,
        latency_ms=latency_ms,
        input_tokens=usage.get("input_tokens") if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
        total_tokens=usage.get("total_tokens") if usage else None,
        finish_reason=str(message.response_metadata.get("finish_reason") or "") or None,
    )


async def stream_role(
    settings: Settings,
    role: ProviderRole,
    prompt: str,
    on_token: Callable[[str], Awaitable[None]],
) -> RoleResponse:
    """Transmite texto incremental e devolve a medição consolidada do provider."""
    resolved = resolve_role(settings, role)
    model = create_chat_model(settings, role)
    started_at = perf_counter()
    first_token_ms: int | None = None
    parts: list[str] = []
    usage: UsageMetadata | None = None
    finish_reason: str | None = None
    async with _semaphore(settings.llm_max_concurrency):
        async for chunk in model.astream([HumanMessage(content=prompt)]):
            text = chunk.text if isinstance(chunk.text, str) else ""
            if text:
                if first_token_ms is None:
                    first_token_ms = round((perf_counter() - started_at) * 1000)
                parts.append(text)
                await on_token(text)
            if chunk.usage_metadata:
                usage = chunk.usage_metadata
            candidate_finish = chunk.response_metadata.get("finish_reason")
            if candidate_finish:
                finish_reason = str(candidate_finish)
    latency_ms = round((perf_counter() - started_at) * 1000)
    return RoleResponse(
        text="".join(parts),
        provider=resolved.provider,
        model=resolved.model,
        latency_ms=latency_ms,
        input_tokens=usage.get("input_tokens") if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
        total_tokens=usage.get("total_tokens") if usage else None,
        time_to_first_token_ms=first_token_ms,
        finish_reason=finish_reason,
    )


async def invoke_role_with_tool(
    settings: Settings, role: ProviderRole, prompt: str, tool: ToolSpec
) -> RoleResponse:
    """Solicita exatamente uma chamada estruturada sem executar a ferramenta."""
    resolved = resolve_role(settings, role)
    model = create_chat_model(settings, role).bind_tools(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
        ],
        tool_choice=tool.name,
    )
    started_at = perf_counter()
    async with _semaphore(settings.llm_max_concurrency):
        message = await model.ainvoke([HumanMessage(content=prompt)])
    latency_ms = round((perf_counter() - started_at) * 1000)
    usage = message.usage_metadata
    calls = tuple(
        ToolCall(name=str(call.get("name", "")), arguments=dict(call.get("args", {})))
        for call in message.tool_calls
    )
    return RoleResponse(
        text=message.text if isinstance(message.text, str) else str(message.content),
        provider=resolved.provider,
        model=resolved.model,
        latency_ms=latency_ms,
        input_tokens=usage.get("input_tokens") if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
        total_tokens=usage.get("total_tokens") if usage else None,
        finish_reason=str(message.response_metadata.get("finish_reason") or "") or None,
        tool_calls=calls,
    )
