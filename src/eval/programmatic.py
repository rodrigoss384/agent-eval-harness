"""Observação programática de latência, tokens e custo."""

from src.models import CandidateInput, EvaluationMethod, EvaluationResult, RunMetrics


def collect_metrics(candidate: CandidateInput) -> tuple[EvaluationResult, RunMetrics]:
    """Registra métricas fornecidas sem inventar valores ausentes."""
    total_tokens = None
    if candidate.input_tokens is not None and candidate.output_tokens is not None:
        total_tokens = candidate.input_tokens + candidate.output_tokens

    cost_reported = candidate.cost_usd is not None
    metrics = RunMetrics(
        latency_ms=candidate.latency_ms,
        input_tokens=candidate.input_tokens,
        output_tokens=candidate.output_tokens,
        total_tokens=total_tokens,
        cost_usd=candidate.cost_usd,
        cost_status="reported" if cost_reported else "unavailable",
        cost_source="provider_response" if cost_reported else "none",
    )
    result = EvaluationResult(
        method=EvaluationMethod.PROGRAMMATIC_CHECK,
        status="observed",
        correctness_definition=(
            "Mede latência, tokens e custo informados; sem thresholds, não altera o veredito."
        ),
        passed=None,
        reason="Métricas observadas sem limite normativo configurado.",
        evidence=metrics.model_dump(mode="json"),
    )
    return result, metrics
