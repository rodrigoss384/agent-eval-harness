"""Orquestra a avaliação offline e persiste o veredito."""

from uuid import uuid4

from src.dataset import find_case
from src.eval.deterministic import evaluate_deterministic
from src.eval.programmatic import collect_metrics
from src.models import EvaluationMethod, FinalVerdict, RunMetrics, RunRequest, RunVerdict, utc_now
from src.storage import SQLiteStore


class CaseNotFoundError(LookupError):
    """Indica referência a um caso ausente no dataset."""


async def run_evaluation(request: RunRequest, store: SQLiteStore) -> RunVerdict:
    """Executa apenas os métodos selecionados e deriva um veredito explícito."""
    case = find_case(request.case_id)
    if case is None:
        raise CaseNotFoundError(request.case_id)

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
    for method in request.methods:
        if method is EvaluationMethod.DETERMINISTIC_MATCH:
            evaluations.append(evaluate_deterministic(case, request.candidate))
        elif method is EvaluationMethod.PROGRAMMATIC_CHECK:
            programmatic, metrics = collect_metrics(request.candidate)
            evaluations.append(programmatic)

    normative = [result for result in evaluations if result.passed is not None]
    final_verdict: FinalVerdict
    if any(result.passed is False for result in normative):
        final_verdict = FinalVerdict.FAIL
    elif normative and all(result.passed is True for result in normative):
        final_verdict = FinalVerdict.PASS
    else:
        final_verdict = FinalVerdict.INCONCLUSIVE

    verdict = RunVerdict(
        run_id=f"run_{uuid4().hex[:12]}",
        case_id=case.id,
        created_at=utc_now(),
        run_status="completed",
        final_verdict=final_verdict,
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
