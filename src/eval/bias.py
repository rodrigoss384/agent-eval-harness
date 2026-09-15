"""Auditorias live de position, preferência de família, verbosidade e definição."""

# ruff: noqa: E501

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from src.config import Settings
from src.eval.datasets import get_dataset
from src.eval.deterministic import evaluate_deterministic
from src.llm.factory import ProviderConfigurationError, ProviderRole, invoke_role, resolve_role
from src.models import (
    BiasAudit,
    BiasAuditAccepted,
    BiasAuditRequest,
    CandidateInput,
    DatasetCase,
    ToolCall,
    utc_now,
)
from src.storage import SQLiteStore


class BiasAuditError(ValueError):
    """Erro legível na preparação de uma auditoria."""


BiasExperiment = Literal["position", "self_preference", "verbosity", "correctness_definition"]


class PairDecision(BaseModel):
    score_a: float = Field(ge=0, le=1)
    score_b: float = Field(ge=0, le=1)
    winner: Literal["A", "B", "tie"]
    reason: str


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start >= 0 < end else text


class BiasAuditManager:
    """Executa experimentos em background e persiste seus resultados."""

    CALLS = {"position": 6, "self_preference": 18, "verbosity": 6, "correctness_definition": 0}

    def __init__(self, settings: Settings, store: SQLiteStore) -> None:
        self._settings = settings
        self._store = store
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def start(
        self, experiment: BiasExperiment, request: BiasAuditRequest
    ) -> BiasAuditAccepted:
        document = await get_dataset(self._store, request.dataset_id)
        if document is None:
            raise BiasAuditError("O dataset informado não existe.")
        case = next((item for item in document.cases if item.id == request.case_id), None)
        if case is None:
            raise BiasAuditError("O caso informado não existe no dataset.")
        try:
            if experiment != "correctness_definition":
                resolve_role(self._settings, "judge_alt")
            if experiment == "self_preference":
                resolve_role(self._settings, "agent")
                resolve_role(self._settings, "judge")
        except ProviderConfigurationError as error:
            raise BiasAuditError(str(error)) from error
        hypotheses = {
            "position": "A ordem dos candidatos pode alterar a preferência do juiz.",
            "self_preference": "Cada família de modelo pode favorecer o candidato da própria família.",
            "verbosity": "Uma resposta inflada pode receber nota maior mesmo sem fatos adicionais.",
            "correctness_definition": "O mesmo trace pode mudar de veredito quando a definição de ferramenta correta muda.",
        }
        protocols = {
            "position": "Três julgamentos A/B e três B/A, com rótulos opacos.",
            "self_preference": "Três pares OpenAI/Gemini, julgados pelas duas famílias nas duas ordens, condicionados à equivalência factual.",
            "verbosity": "Versões factual-equivalentes concisa e inflada, três vezes em cada ordem.",
            "correctness_definition": "Aplica tool_exact e tool_canonical ao mesmo trace, sem LLM.",
        }
        now = utc_now()
        audit = BiasAudit(
            audit_id=f"audit_{uuid4().hex[:12]}",
            experiment=experiment,
            created_at=now,
            updated_at=now,
            status="queued",
            hypothesis=hypotheses[experiment],
            protocol=protocols[experiment],
            calls_planned=self.CALLS[experiment],
        )
        await self._persist(audit)
        self._tasks[audit.audit_id] = asyncio.create_task(
            self._execute(audit, case), name=audit.audit_id
        )
        return BiasAuditAccepted(
            audit_id=audit.audit_id,
            events_url=f"/api/eval/bias/{audit.audit_id}/events",
            calls_planned=audit.calls_planned,
        )

    async def get(self, audit_id: str) -> BiasAudit | None:
        document = await self._store.get_bias_audit(audit_id)
        return None if document is None else BiasAudit.model_validate_json(document)

    async def list(self, limit: int, offset: int) -> list[BiasAudit]:
        return [
            BiasAudit.model_validate_json(item)
            for item in await self._store.list_bias_audits(limit, offset)
        ]

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def events(self, audit_id: str, after: int) -> AsyncIterator[dict[str, Any]]:
        snapshot = await self.get(audit_id)
        if snapshot is None:
            raise BiasAuditError("Auditoria não encontrada.")
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[audit_id].add(queue)
        try:
            for event in await self._store.list_bias_events(audit_id, after):
                yield event
            yield {"event_type": "snapshot", "payload": snapshot.model_dump(mode="json")}
            if snapshot.status in {"completed", "failed", "cancelled", "interrupted"}:
                return
            while True:
                event = await queue.get()
                yield event
                if event["event_type"] in {"audit_completed", "audit_failed"}:
                    return
        finally:
            self._subscribers[audit_id].discard(queue)

    async def _persist(self, audit: BiasAudit) -> None:
        audit.updated_at = utc_now()
        await self._store.save_bias_audit(audit.audit_id, audit.experiment, audit.model_dump_json())

    async def _emit(self, audit: BiasAudit, event_type: str, payload: dict[str, Any]) -> None:
        cursor = await self._store.append_bias_event(
            audit.audit_id, event_type, json.dumps(payload, ensure_ascii=False)
        )
        audit.event_cursor = cursor
        await self._persist(audit)
        event = {"event_id": cursor, "event_type": event_type, "payload": payload}
        for queue in tuple(self._subscribers[audit.audit_id]):
            await queue.put(event)

    async def _judge_pair(
        self, role: ProviderRole, case: DatasetCase, first: str, second: str
    ) -> PairDecision:
        prompt = f"""Compare duas respostas usando somente a definição e rubrica. Rótulos não indicam qualidade.
Os scores são decimais no intervalo fechado 0.0 a 1.0; nunca use escala 0 a 5 ou 0 a 10.
Retorne APENAS JSON: {{"score_a":0.0,"score_b":0.0,"winner":"A|B|tie","reason":"..."}}.
PERGUNTA: {case.input}
DEFINIÇÃO: {case.correctness_definition}
RUBRICA: {json.dumps(case.rubric, ensure_ascii=False)}
RESPOSTA A: {first}
RESPOSTA B: {second}"""
        response = await invoke_role(self._settings, role, prompt)
        return PairDecision.model_validate_json(_extract_json(response.text))

    async def _execute(self, audit: BiasAudit, case: DatasetCase) -> None:
        try:
            audit.status = "running"
            await self._emit(audit, "audit_started", {"experiment": audit.experiment})
            if audit.experiment == "position":
                await self._position(audit, case)
            elif audit.experiment == "self_preference":
                await self._self_preference(audit, case)
            elif audit.experiment == "verbosity":
                await self._verbosity(audit, case)
            else:
                await self._correctness_definition(audit, case)
            audit.status = "completed"
            await self._emit(audit, "audit_completed", audit.model_dump(mode="json"))
        except Exception as error:  # noqa: BLE001
            audit.status = "failed"
            audit.result = "inconclusive"
            audit.error = f"{type(error).__name__}: {error}"
            await self._emit(audit, "audit_failed", {"error": audit.error})
        finally:
            self._tasks.pop(audit.audit_id, None)

    async def _position(self, audit: BiasAudit, case: DatasetCase) -> None:
        good = case.expected_output
        weak = "Não há informação suficiente para responder."
        observations: list[dict[str, Any]] = []
        good_first: list[float] = []
        good_second: list[float] = []
        for repetition in range(1, 4):
            ab = await self._judge_pair("judge_alt", case, good, weak)
            ba = await self._judge_pair("judge_alt", case, weak, good)
            good_first.append(ab.score_a)
            good_second.append(ba.score_b)
            observations.append(
                {
                    "repetition": repetition,
                    "ab": ab.model_dump(),
                    "ba": ba.model_dump(),
                    "winner_inverted": ab.winner == "A" and ba.winner != "B",
                }
            )
            await self._emit(audit, "measurement_completed", observations[-1])
        audit.delta = sum(good_first) / 3 - sum(good_second) / 3
        inversions = sum(bool(item["winner_inverted"]) for item in observations)
        audit.result = (
            "detected" if inversions or round(abs(audit.delta), 6) >= 0.1 else "not_detected"
        )
        audit.measurements = {
            "good_score_position_1": good_first,
            "good_score_position_2": good_second,
            "inversions": inversions,
            "observations": observations,
        }
        audit.limitations = [
            "A auditoria mede este caso, modelo e momento; não estima prevalência geral."
        ]

    async def _self_preference(self, audit: BiasAudit, case: DatasetCase) -> None:
        judge = resolve_role(self._settings, "judge")
        alt = resolve_role(self._settings, "judge_alt")
        if (judge.provider, judge.model) == (alt.provider, alt.model):
            audit.result = "inconclusive"
            audit.limitations = ["Os dois juízes usam o mesmo provider e modelo."]
            return
        context = "\n".join(chunk.text for chunk in case.reference_context)
        prompt = (
            f"Responda somente com base no contexto. Pergunta: {case.input}\nContexto:\n{context}"
        )
        pairs: list[dict[str, Any]] = []
        own_advantages: list[float] = []
        for repetition in range(1, 4):
            openai_candidate = await invoke_role(self._settings, "agent", prompt)
            gemini_candidate = await invoke_role(self._settings, "judge_alt", prompt)
            first_ok = (
                evaluate_deterministic(case, CandidateInput(output=openai_candidate.text)).passed
                is True
            )
            second_ok = (
                evaluate_deterministic(case, CandidateInput(output=gemini_candidate.text)).passed
                is True
            )
            if not (first_ok and second_ok):
                pairs.append({"repetition": repetition, "equivalent": False})
                audit.measurements = {"pairs": pairs, "equivalent_pairs": len(own_advantages)}
                await self._emit(audit, "measurement_completed", pairs[-1])
                continue
            evaluations: dict[str, Any] = {}
            for role in ("judge", "judge_alt"):
                ab = await self._judge_pair(
                    role, case, openai_candidate.text, gemini_candidate.text
                )
                ba = await self._judge_pair(
                    role, case, gemini_candidate.text, openai_candidate.text
                )
                evaluations[role] = {"ab": ab.model_dump(), "ba": ba.model_dump()}
            openai_by_openai = (
                evaluations["judge"]["ab"]["score_a"] + evaluations["judge"]["ba"]["score_b"]
            ) / 2
            openai_by_gemini = (
                evaluations["judge_alt"]["ab"]["score_a"]
                + evaluations["judge_alt"]["ba"]["score_b"]
            ) / 2
            gemini_by_gemini = (
                evaluations["judge_alt"]["ab"]["score_b"]
                + evaluations["judge_alt"]["ba"]["score_a"]
            ) / 2
            gemini_by_openai = (
                evaluations["judge"]["ab"]["score_b"] + evaluations["judge"]["ba"]["score_a"]
            ) / 2
            advantage = (
                (openai_by_openai - openai_by_gemini) + (gemini_by_gemini - gemini_by_openai)
            ) / 2
            own_advantages.append(advantage)
            pairs.append(
                {
                    "repetition": repetition,
                    "equivalent": True,
                    "own_family_advantage": advantage,
                    "evaluations": evaluations,
                }
            )
            audit.measurements = {
                "pairs": pairs,
                "equivalent_pairs": len(own_advantages),
            }
            await self._emit(audit, "measurement_completed", pairs[-1])
        if not own_advantages:
            audit.result = "inconclusive"
            audit.limitations = ["Nenhum par cumpriu a equivalência factual determinística."]
            audit.measurements = {"pairs": pairs}
            return
        audit.delta = sum(own_advantages) / len(own_advantages)
        audit.result = "detected" if round(audit.delta, 6) >= 0.1 else "not_detected"
        audit.measurements = {"pairs": pairs, "equivalent_pairs": len(own_advantages)}
        audit.limitations = [
            "Equivalência cobre os fatos declarados, não equivalência semântica total."
        ]

    async def _verbosity(self, audit: BiasAudit, case: DatasetCase) -> None:
        concise = case.expected_output
        inflated = (
            concise
            + " Em termos gerais, esta análise merece atenção cuidadosa, acompanhamento contínuo e comunicação entre todas as partes interessadas, sem acrescentar novos fatos ao caso."
        )
        concise_scores: list[float] = []
        inflated_scores: list[float] = []
        observations = []
        for repetition in range(1, 4):
            ci = await self._judge_pair("judge_alt", case, concise, inflated)
            ic = await self._judge_pair("judge_alt", case, inflated, concise)
            concise_scores.extend([ci.score_a, ic.score_b])
            inflated_scores.extend([ci.score_b, ic.score_a])
            observations.append(
                {
                    "repetition": repetition,
                    "concise_first": ci.model_dump(),
                    "inflated_first": ic.model_dump(),
                }
            )
            await self._emit(audit, "measurement_completed", observations[-1])
        audit.delta = sum(inflated_scores) / len(inflated_scores) - sum(concise_scores) / len(
            concise_scores
        )
        audit.result = "detected" if round(audit.delta, 6) >= 0.1 else "not_detected"
        audit.measurements = {
            "concise_scores": concise_scores,
            "inflated_scores": inflated_scores,
            "observations": observations,
        }
        audit.limitations = [
            "A versão inflada é controlada, mas o efeito depende da rubrica e do caso."
        ]

    async def _correctness_definition(self, audit: BiasAudit, case: DatasetCase) -> None:
        tool_case = case
        if tool_case.tool is None:
            document = await get_dataset(self._store, "builtin-v2")
            assert document is not None
            tool_case = next(
                item for item in document.cases if item.tool and item.tool.canonical_aliases
            )
        assert tool_case.tool is not None
        alias = tool_case.tool.canonical_aliases[0]
        candidate = CandidateInput(
            output="",
            tool_calls=[ToolCall(name=alias, arguments=tool_case.tool.expected_arguments)],
        )
        exact = tool_case.model_copy(deep=True)
        exact.deterministic_rule.kind = "tool_exact"
        canonical = tool_case.model_copy(deep=True)
        canonical.deterministic_rule.kind = "tool_canonical"
        exact_result = evaluate_deterministic(exact, candidate)
        canonical_result = evaluate_deterministic(canonical, candidate)
        audit.result = (
            "detected" if exact_result.passed != canonical_result.passed else "not_detected"
        )
        audit.delta = 1.0 if audit.result == "detected" else 0.0
        audit.measurements = {
            "trace": candidate.model_dump(mode="json"),
            "tool_exact": exact_result.model_dump(mode="json"),
            "tool_canonical": canonical_result.model_dump(mode="json"),
        }
        audit.limitations = [
            "Demonstra sensibilidade à regra declarada; não executa ferramenta externa."
        ]
