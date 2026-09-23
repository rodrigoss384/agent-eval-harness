"""Despacho comum: erros de um juiz não apagam o resultado do outro."""

import json

from src.config import Settings
from src.eval.context import PROTOCOL_VERSION, evaluation_state
from src.eval.decision import evaluate_with_decision_model
from src.eval.judge import evaluate_with_judge
from src.llm.factory import ProviderConfigurationError, ProviderRole
from src.models import (
    CandidateInput,
    DatasetCase,
    EvaluationMethod,
    EvaluationMetrics,
    EvaluationResult,
)


def candidate_output(candidate: CandidateInput) -> str:
    if not candidate.tool_calls:
        return candidate.output
    return json.dumps(
        {
            "text": candidate.output,
            "tool_calls": [call.model_dump() for call in candidate.tool_calls],
        },
        ensure_ascii=False,
    )


async def evaluate_model(
    settings: Settings,
    case: DatasetCase,
    output: str,
    method: EvaluationMethod,
    role: ProviderRole = "judge",
    pricing_profile: str = "standard",
) -> EvaluationResult:
    try:
        if method == EvaluationMethod.DECISION_MODEL:
            return await evaluate_with_decision_model(settings, case, output)
        result, *_ = await evaluate_with_judge(settings, case, output, role, pricing_profile)
        return result
    except Exception as error:
        metrics = getattr(error, "metrics", None)
        return EvaluationResult(
            method=method,
            status="unavailable" if isinstance(error, ProviderConfigurationError) else "error",
            correctness_definition=case.correctness_definition,
            threshold=case.threshold,
            rubric=case.rubric,
            reason=(
                str(error)
                if isinstance(error, ProviderConfigurationError)
                else f"{type(error).__name__}: julgamento indisponível; sem retry automático."
            ),
            judge_provider="openrouter"
            if method == EvaluationMethod.DECISION_MODEL
            else getattr(settings, f"eval_{role}_provider"),
            judge_model=settings.jev_model
            if method == EvaluationMethod.DECISION_MODEL
            else getattr(settings, f"eval_{role}_model"),
            evidence={"error_type": type(error).__name__},
            metrics=metrics
            if isinstance(metrics, EvaluationMetrics)
            else EvaluationMetrics(),
            score_type="probability" if method == EvaluationMethod.DECISION_MODEL else "rating",
            rationale_available=False,
            protocol_version=PROTOCOL_VERSION,
            evaluated_state=evaluation_state(case, output),
        )
