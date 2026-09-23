"""Orquestra a avaliação offline e persiste o veredito."""

from time import perf_counter
from uuid import uuid4

from src.config import Settings
from src.dataset import find_case
from src.eval.deterministic import evaluate_deterministic
from src.eval.dispatch import candidate_output, evaluate_model
from src.eval.programmatic import collect_metrics
from src.eval.telemetry import combine_metrics, final_verdict
from src.models import (
    EvaluationMethod,
    EvaluationMetrics,
    RunMetrics,
    RunRequest,
    RunVerdict,
    utc_now,
)
from src.storage import SQLiteStore


class CaseNotFoundError(LookupError):
    """Indica referência a um caso ausente no dataset."""


async def run_evaluation(
    request: RunRequest, store: SQLiteStore, settings: Settings | None = None
) -> RunVerdict:
    """Executa apenas os métodos selecionados e deriva um veredito explícito."""
    case = find_case(request.case_id)
    if case is None:
        raise CaseNotFoundError(request.case_id)

    started = perf_counter()
    evaluations = []
    metrics = RunMetrics(
        latency_ms=request.candidate.latency_ms,
        input_tokens=request.candidate.input_tokens,
        output_tokens=request.candidate.output_tokens,
        total_tokens=None,
        cost_usd=request.candidate.cost_usd,
        cost_status="reported" if request.candidate.cost_usd is not None else "unavailable",
        cost_source="provider_response" if request.candidate.cost_usd is not None else "none",
    )
    for method in dict.fromkeys(request.methods):
        if method is EvaluationMethod.DETERMINISTIC_MATCH:
            evaluations.append(evaluate_deterministic(case, request.candidate))
        elif method is EvaluationMethod.PROGRAMMATIC_CHECK:
            programmatic, metrics = collect_metrics(request.candidate)
            evaluations.append(programmatic)

        elif method in {EvaluationMethod.LLM_AS_JUDGE, EvaluationMethod.DECISION_MODEL}:
            evaluations.append(
                await evaluate_model(
                    settings or Settings(),
                    case,
                    candidate_output(request.candidate),
                    method,
                )
            )

    verdict_value = final_verdict(evaluations)
    if any(item.method in {"llm_as_judge", "decision_model"} for item in evaluations):
        candidate = request.candidate
        has_metrics = any(
            value is not None
            for value in (
                candidate.latency_ms,
                candidate.input_tokens,
                candidate.output_tokens,
                candidate.cost_usd,
            )
        )
        agent = (
            EvaluationMetrics(
                latency_ms=candidate.latency_ms,
                input_tokens=candidate.input_tokens,
                output_tokens=candidate.output_tokens,
                total_tokens=candidate.input_tokens + candidate.output_tokens
                if candidate.input_tokens is not None and candidate.output_tokens is not None
                else None,
                cost_usd=candidate.cost_usd,
                cost_status="reported" if candidate.cost_usd is not None else "unavailable",
                cost_source="provider_response" if candidate.cost_usd is not None else "none",
            )
            if has_metrics
            else None
        )
        metrics = combine_metrics(agent, evaluations, round((perf_counter() - started) * 1000))

    verdict = RunVerdict(
        run_id=f"run_{uuid4().hex[:12]}",
        case_id=case.id,
        created_at=utc_now(),
        run_status="partial"
        if any(e.status in {"error", "unavailable"} for e in evaluations)
        else "completed",
        final_verdict=verdict_value,
        candidate_origin="supplied_trace",
        agent_input=case.input,
        agent_output=request.candidate.output,
        tool_calls=request.candidate.tool_calls,
        evaluations=evaluations,
        metrics=metrics,
    )
    await store.save_run(
        verdict.run_id,
        verdict.case_id,
        verdict.model_dump_json(),
    )
    return verdict
