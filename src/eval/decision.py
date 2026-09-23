"""Avaliação probabilística sem inventar racional textual."""

from src.config import Settings
from src.eval.context import PROTOCOL_VERSION, evaluation_state
from src.llm.jev import request_decision
from src.models import DatasetCase, EvaluationMethod, EvaluationResult


async def evaluate_with_decision_model(
    settings: Settings, case: DatasetCase, output: str
) -> EvaluationResult:
    state = evaluation_state(case, output)
    response = await request_decision(settings, state)
    passed = response.probability >= case.threshold
    return EvaluationResult(
        method=EvaluationMethod.DECISION_MODEL,
        status="passed" if passed else "failed",
        passed=passed,
        correctness_definition=case.correctness_definition,
        reason=(
            f"Decision model: p={response.probability:.6g} de atender ao "
            f"critério; sem racional textual."
        ),
        score=response.probability,
        threshold=case.threshold,
        rubric=case.rubric,
        judge_model=response.model,
        judge_provider="openrouter",
        upstream_provider=response.provider,
        request_id=response.request_id,
        metrics=response.metrics,
        score_type="probability",
        rationale_available=False,
        protocol_version=PROTOCOL_VERSION,
        evaluated_state=state,
    )
