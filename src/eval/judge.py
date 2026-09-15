"""LLM-as-judge com contrato fechado e parsing sem reparo automático."""

import json
import re

from pydantic import BaseModel, Field, ValidationError

from src.config import Settings
from src.llm.factory import ProviderRole, invoke_role
from src.models import DatasetCase, EvaluationMethod, EvaluationResult


class JudgeDecision(BaseModel):
    """Formato obrigatório da decisão emitida pelo juiz."""

    score: float = Field(ge=0, le=1)
    passed: bool
    reason: str = Field(min_length=20)
    evidence: list[str] = Field(min_length=1)


class JudgeParseError(ValueError):
    """Preserva como erro uma resposta que não cumpre o contrato."""


def _json_object(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


async def evaluate_with_judge(
    settings: Settings, case: DatasetCase, output: str, role: ProviderRole
) -> tuple[EvaluationResult, int | None, int | None, int | None, int]:
    """Julga uma resposta e retorna também usage e latência reais."""
    prompt = f"""Você é um juiz de avaliação independente. Avalie somente pelos dados abaixo.
Retorne APENAS JSON: {{"score":0.0,"passed":false,"reason":"...","evidence":["..."]}}.
O campo passed deve ser score >= {case.threshold}. O racional deve citar evidências concretas.

PERGUNTA:
{case.input}

GROUND TRUTH:
{case.expected_output}

DEFINIÇÃO DE CORRETO:
{case.correctness_definition}

RUBRICA:
{json.dumps(case.rubric, ensure_ascii=False)}

RESPOSTA DO AGENTE:
{output}
"""
    response = await invoke_role(settings, role, prompt)
    try:
        decision = JudgeDecision.model_validate_json(_json_object(response.text))
    except (ValidationError, json.JSONDecodeError) as error:
        raise JudgeParseError(
            "O juiz retornou JSON incompatível com o contrato fechado."
        ) from error
    passed = decision.passed and decision.score >= case.threshold
    result = EvaluationResult(
        method=EvaluationMethod.LLM_AS_JUDGE,
        status="passed" if passed else "failed",
        correctness_definition=case.correctness_definition,
        passed=passed,
        reason=decision.reason,
        evidence={"judge_evidence": decision.evidence},
        judge_model=response.model,
        rubric=case.rubric,
        score=decision.score,
        threshold=case.threshold,
    )
    return (
        result,
        response.input_tokens,
        response.output_tokens,
        response.total_tokens,
        response.latency_ms,
    )
