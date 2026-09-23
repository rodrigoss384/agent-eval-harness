"""Cliente Decisions: uma chamada, sem chat/completions, retries ou reparos."""

import math
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from src.config import Settings
from src.eval.context import DECISION_QUESTION
from src.eval.pricing import estimate_cost
from src.llm.factory import ProviderConfigurationError, _semaphore
from src.models import EvaluationMetrics


class JevContractError(ValueError):
    """Resposta inválida, sem reproduzir conteúdo privado do provider."""


@dataclass(frozen=True)
class DecisionResponse:
    probability: float
    model: str
    metrics: EvaluationMetrics
    request_id: str | None = None
    provider: str | None = None


def jev_key(settings: Settings) -> str:
    key = settings.jev_api_key or settings.openrouter_api_key
    if settings.jev_api_key and not settings.jev_api_key.get_secret_value().strip():
        key = settings.openrouter_api_key
    if key is None or not key.get_secret_value().strip():
        raise ProviderConfigurationError("Configure JEV_API_KEY ou OPENROUTER_API_KEY para Jev.")
    return key.get_secret_value()


def _usage_integer(usage: dict[str, Any], name: str) -> int | None:
    value = usage.get(name)
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise JevContractError("Jev retornou usage inválido.")
    return value


async def request_decision(
    settings: Settings, state: str, *, client: httpx.AsyncClient | None = None
) -> DecisionResponse:
    key = jev_key(settings)
    if not settings.jev_model.strip():
        raise ProviderConfigurationError("JEV_MODEL não pode estar vazio.")
    payload = {
        "model": settings.jev_model,
        "state": state,
        "questions": {"passed": {"type": "noul", "instructions": DECISION_QUESTION}},
    }
    queued = perf_counter()
    async with _semaphore(settings.llm_max_concurrency):
        started = perf_counter()

        async def send(http: httpx.AsyncClient) -> httpx.Response:
            return await http.post(
                settings.jev_base_url,
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=settings.llm_timeout_seconds,
            )

        if client is None:
            async with httpx.AsyncClient() as http:
                response = await send(http)
        else:
            response = await send(client)
        elapsed = round((perf_counter() - started) * 1000)
    if response.status_code < 200 or response.status_code >= 300:
        raise JevContractError(f"Jev respondeu HTTP {response.status_code}; sem nova tentativa.")
    try:
        body = response.json()
        answer = body["answers"]["passed"]
        probability = answer["noul"]
        if (
            answer.get("type") != "noul"
            or type(probability) not in (float, int)
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        ):
            raise ValueError("probability")
        model = body["model"]
        if not isinstance(model, str) or not model:
            raise ValueError("model")
        usage = body.get("usage", {})
        input_tokens = _usage_integer(usage, "input_tokens")
        output_tokens = _usage_integer(usage, "output_tokens")
        cost = usage.get("cost")
        if cost is not None and (
            type(cost) not in (float, int) or not math.isfinite(cost) or cost < 0
        ):
            raise ValueError("cost")
        metrics = EvaluationMetrics(
            latency_ms=elapsed,
            queue_ms=round((started - queued) * 1000),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None,
            cost_usd=cost,
            cost_status="reported" if cost is not None else "unavailable",
            cost_source="provider_response" if cost is not None else "none",
        )
        if cost is None:
            estimate = estimate_cost(
                model=model,
                pricing_profile="standard",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            if estimate.usd is not None:
                metrics.cost_usd = estimate.usd
                metrics.cost_status = "estimated"
                metrics.cost_source = "pricing_catalog"
                metrics.cost_formula = estimate.formula
                metrics.pricing_version = estimate.catalog_version
        return DecisionResponse(
            float(probability),
            model,
            metrics,
            body.get("id") if isinstance(body.get("id"), str) else None,
            body.get("provider") if isinstance(body.get("provider"), str) else None,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise JevContractError(
            "Jev retornou uma resposta incompatível com o contrato noul."
        ) from error
