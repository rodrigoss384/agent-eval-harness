"""Métricas por chamada e agregação sem zeros inventados."""

from src.eval.pricing import estimate_cost
from src.llm.factory import RoleResponse
from src.models import EvaluationMetrics, EvaluationResult, FinalVerdict, RunMetrics


def response_metrics(response: RoleResponse, profile: str = "standard") -> EvaluationMetrics:
    estimate = estimate_cost(
        model=response.model,
        pricing_profile=profile,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cached_input_tokens=response.cached_input_tokens,
    )
    reported = response.cost_usd is not None
    cost = response.cost_usd if reported else estimate.usd
    return EvaluationMetrics(
        latency_ms=response.latency_ms,
        queue_ms=response.queue_ms,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=response.total_tokens,
        cached_input_tokens=response.cached_input_tokens,
        cost_usd=cost,
        cost_status="reported" if reported else "estimated" if cost is not None else "unavailable",
        cost_source="provider_response"
        if reported
        else "pricing_catalog"
        if cost is not None
        else "none",
        cost_formula=None if reported else estimate.formula or None,
        pricing_version=None if reported else estimate.catalog_version,
    )


def final_verdict(evaluations: list[EvaluationResult]) -> FinalVerdict:
    if any(item.passed is False for item in evaluations):
        return FinalVerdict.FAIL
    if any(item.status in {"error", "unavailable"} for item in evaluations):
        return FinalVerdict.INCONCLUSIVE
    return (
        FinalVerdict.PASS
        if any(item.passed is True for item in evaluations)
        else FinalVerdict.INCONCLUSIVE
    )


def combine_metrics(
    agent: EvaluationMetrics | None, evaluations: list[EvaluationResult], total_ms: int
) -> RunMetrics:
    judges = [
        item.metrics or EvaluationMetrics()
        for item in evaluations
        if item.method in {"llm_as_judge", "decision_model"}
    ]
    parts = ([agent] if agent is not None else []) + judges

    def total(field: str) -> int | None:
        values = [getattr(part, field) for part in parts]
        return sum(values) if values and all(value is not None for value in values) else None

    known = bool(parts) and all(part.cost_usd is not None for part in parts)
    sources = {p.cost_source for p in parts}
    return RunMetrics(
        latency_ms=total_ms,
        total_latency_ms=total_ms,
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        total_tokens=total("total_tokens"),
        cost_usd=sum(p.cost_usd or 0 for p in parts) if known else None,
        cost_status=("reported" if all(p.cost_status == "reported" for p in parts) else "estimated")
        if known
        else "unavailable",
        cost_source=(next(iter(sources)) if len(sources) == 1 else "mixed") if known else "none",
        generation_ms=agent.latency_ms if agent else None,
        judge_ms=sum(p.latency_ms or 0 for p in judges) if judges else None,
        agent_metrics=agent,
    )
