"""Orquestra sessões live, tentativas reais e eventos incrementais."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from typing import Any
from uuid import uuid4

from src.config import Settings
from src.eval.aggregation import aggregate_trials
from src.eval.datasets import get_dataset
from src.eval.deterministic import evaluate_deterministic
from src.eval.judge import evaluate_with_judge
from src.eval.pricing import estimate_cost
from src.eval.retrieval import retrieve_chunks
from src.llm.factory import (
    ProviderConfigurationError,
    invoke_role_with_tool,
    resolve_role,
    stream_role,
)
from src.models import (
    CandidateInput,
    DatasetCase,
    EvaluationMethod,
    EvaluationResult,
    EvaluationSession,
    FinalVerdict,
    RunMetrics,
    RunVerdict,
    SessionAccepted,
    SessionRequest,
    utc_now,
)
from src.storage import SQLiteStore


class LiveSessionError(ValueError):
    """Erro público e legível ao criar ou consultar uma sessão."""


class LiveSessionNotFoundError(LiveSessionError):
    """Distingue ausência de sessão de configuração inválida."""


def _sum_available(*values: int | None) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


class LiveEvaluationManager:
    """Mantém tasks e subscribers em memória; snapshots ficam no SQLite."""

    def __init__(self, settings: Settings, store: SQLiteStore) -> None:
        self._settings = settings
        self._store = store
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
        self._session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._shutting_down = False

    async def start(self, request: SessionRequest) -> SessionAccepted:
        """Valida dependências, persiste a sessão e só então agenda execução."""
        document = await get_dataset(self._store, request.dataset_id)
        if document is None:
            raise LiveSessionError("O dataset informado não existe.")
        known = {case.id for case in document.cases}
        missing = [case_id for case_id in request.case_ids if case_id not in known]
        if missing:
            raise LiveSessionError(f"Casos ausentes no dataset: {', '.join(missing)}")
        if request.mode == "single" and len(request.case_ids) != 1:
            raise LiveSessionError("O modo single exige exatamente um caso.")
        try:
            resolve_role(self._settings, "agent")
            if EvaluationMethod.LLM_AS_JUDGE in request.methods:
                resolve_role(self._settings, request.judge_role)
        except ProviderConfigurationError as error:
            raise LiveSessionError(str(error)) from error
        now = utc_now()
        session = EvaluationSession(
            session_id=f"session_{uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
            status="queued",
            request=request,
        )
        await self._persist(session)
        cases = [case for case in document.cases if case.id in request.case_ids]
        self._tasks[session.session_id] = asyncio.create_task(
            self._execute(session, cases), name=session.session_id
        )
        judge_calls = 1 if EvaluationMethod.LLM_AS_JUDGE in request.methods else 0
        return SessionAccepted(
            session_id=session.session_id,
            events_url=f"/api/eval/sessions/{session.session_id}/events",
            calls_planned=len(cases) * request.trials * (1 + judge_calls),
        )

    async def get(self, session_id: str) -> EvaluationSession | None:
        document = await self._store.get_session(session_id)
        return None if document is None else EvaluationSession.model_validate_json(document)

    async def list(self, limit: int, offset: int) -> list[EvaluationSession]:
        return [
            EvaluationSession.model_validate_json(item)
            for item in await self._store.list_sessions(limit, offset)
        ]

    async def cancel(self, session_id: str) -> EvaluationSession:
        session = await self.get(session_id)
        if session is None:
            raise LiveSessionNotFoundError("Sessão não encontrada.")
        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        return await self.get(session_id) or session

    async def shutdown(self) -> None:
        self._shutting_down = True
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def events(self, session_id: str, after: int) -> AsyncIterator[dict[str, Any]]:
        if await self.get(session_id) is None:
            raise LiveSessionNotFoundError("Sessão não encontrada.")
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers[session_id].add(queue)
        try:
            for event in await self._store.list_session_events(session_id, after):
                yield event
            snapshot = await self.get(session_id)
            if snapshot:
                yield {"event_type": "snapshot", "payload": snapshot.model_dump(mode="json")}
                if snapshot.status in {
                    "completed",
                    "partial",
                    "failed",
                    "cancelled",
                    "interrupted",
                }:
                    return
            while True:
                event = await queue.get()
                yield event
                if event["event_type"] in {
                    "session_completed",
                    "session_partial",
                    "session_failed",
                    "session_cancelled",
                    "session_interrupted",
                }:
                    return
        finally:
            self._subscribers[session_id].discard(queue)

    async def _persist(self, session: EvaluationSession) -> None:
        session.updated_at = utc_now()
        await self._store.save_session(
            session.session_id, session.status, session.model_dump_json()
        )

    async def _emit(
        self,
        session: EvaluationSession,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
    ) -> None:
        event: dict[str, Any] = {"event_type": event_type, "payload": payload}
        if persist:
            async with self._session_locks[session.session_id]:
                cursor = await self._store.append_session_event(
                    session.session_id, event_type, json.dumps(payload, ensure_ascii=False)
                )
                session.event_cursor = cursor
                await self._persist(session)
            event["event_id"] = cursor
        for queue in tuple(self._subscribers[session.session_id]):
            if queue.full() and event_type == "generation_token":
                continue
            await queue.put(event)

    async def _execute(self, session: EvaluationSession, cases: Sequence[DatasetCase]) -> None:
        try:
            session.status = "running"
            await self._emit(
                session, "session_started", {"status": "running", "case_count": len(cases)}
            )
            limiter = asyncio.Semaphore(session.request.concurrency)

            async def run_case(case: DatasetCase) -> None:
                async with limiter:
                    await self._execute_case(session, case)

            await asyncio.gather(*(run_case(case) for case in cases))
            statuses = list(session.case_statuses.values())
            if statuses and all(status == "stable_pass" for status in statuses):
                session.final_verdict = FinalVerdict.PASS
            elif "stable_fail" in statuses:
                session.final_verdict = FinalVerdict.FAIL
            else:
                session.final_verdict = FinalVerdict.INCONCLUSIVE
            session.status = (
                "completed" if session.final_verdict is not FinalVerdict.INCONCLUSIVE else "partial"
            )
            session.current_case_id = None
            session.current_trial = None
            event = "session_completed" if session.status == "completed" else "session_partial"
            await self._emit(
                session, event, {"status": session.status, "final_verdict": session.final_verdict}
            )
        except asyncio.CancelledError:
            session.status = "interrupted" if self._shutting_down else "cancelled"
            session.error = (
                "Execução interrompida pelo encerramento do serviço."
                if self._shutting_down
                else "Execução cancelada pela pessoa usuária."
            )
            await self._emit(session, f"session_{session.status}", {"status": session.status})
            raise
        except Exception as error:  # noqa: BLE001
            session.status = "failed"
            session.error = f"{type(error).__name__}: {error}"
            await self._emit(
                session, "session_failed", {"status": "failed", "error": session.error}
            )
        finally:
            self._tasks.pop(session.session_id, None)

    async def _execute_case(self, session: EvaluationSession, case: DatasetCase) -> None:
        if session.request.mode == "single":
            session.current_case_id = case.id
        await self._emit(session, "case_started", {"case_id": case.id})
        verdicts: list[FinalVerdict] = []
        for trial in range(1, 4):
            if session.request.mode == "single":
                session.current_trial = trial
            try:
                run = await self._run_trial(session, case, trial)
            except Exception as error:  # noqa: BLE001
                verdicts.append(FinalVerdict.INCONCLUSIVE)
                await self._emit(
                    session,
                    "trial_failed",
                    {
                        "case_id": case.id,
                        "trial": trial,
                        "error": f"{type(error).__name__}: {error}",
                    },
                )
                continue
            async with self._session_locks[session.session_id]:
                session.runs.append(run)
                await self._persist(session)
            verdicts.append(run.final_verdict)
            await self._emit(
                session,
                "trial_completed",
                {"case_id": case.id, "trial": trial, "run": run.model_dump(mode="json")},
            )
        session.case_statuses[case.id] = aggregate_trials(verdicts)
        await self._emit(
            session,
            "case_completed",
            {"case_id": case.id, "status": session.case_statuses[case.id]},
        )

    async def _run_trial(
        self, session: EvaluationSession, case: DatasetCase, trial: int
    ) -> RunVerdict:
        ranked = retrieve_chunks(
            case.input,
            case.reference_context,
            case.retrieval.top_k if case.retrieval else len(case.reference_context),
        )
        context = "\n\n".join(f"[{item.chunk.id}] {item.chunk.text}" for item in ranked)
        await self._emit(
            session,
            "retrieval_completed",
            {
                "case_id": case.id,
                "trial": trial,
                "chunks": [{"id": item.chunk.id, "score": item.score} for item in ranked],
            },
        )
        await self._emit(session, "generation_started", {"case_id": case.id, "trial": trial})
        started = asyncio.get_running_loop().time()
        if case.category == "tool_use" and case.tool:
            agent = await invoke_role_with_tool(
                self._settings,
                "agent",
                f"Selecione a ferramenta e preencha somente os argumentos pedidos. Tarefa: {case.input}",
                case.tool,
            )
        else:
            prompt = f"Responda em pt-BR usando somente as fontes. Inclua IDs entre colchetes.\n\nPERGUNTA:\n{case.input}\n\nFONTES:\n{context}"

            async def on_token(token: str) -> None:
                await self._emit(
                    session,
                    "generation_token",
                    {"case_id": case.id, "trial": trial, "token": token},
                    persist=False,
                )

            agent = await stream_role(self._settings, "agent", prompt, on_token)
        serialized_calls = [call.model_dump(mode="json") for call in agent.tool_calls]
        output = agent.text or (
            json.dumps(serialized_calls, ensure_ascii=False) if serialized_calls else ""
        )
        await self._emit(
            session,
            "generation_completed",
            {"case_id": case.id, "trial": trial, "output": output, "tool_calls": serialized_calls},
        )
        candidate = CandidateInput(output=output, tool_calls=list(agent.tool_calls))
        evaluations: list[EvaluationResult] = []
        if EvaluationMethod.DETERMINISTIC_MATCH in session.request.methods:
            deterministic = evaluate_deterministic(case, candidate)
            if case.retrieval:
                selected = {item.chunk.id for item in ranked}
                expected = set(case.retrieval.expected_context_ids)
                deterministic.evidence["retrieval"] = {
                    "recall_at_k": len(selected & expected) / len(expected),
                    "precision_at_k": len(selected & expected) / len(selected) if selected else 0,
                    "selected_ids": sorted(selected),
                    "expected_ids": sorted(expected),
                }
            evaluations.append(deterministic)
        judge_input = judge_output = judge_total = None
        judge_ms = 0
        if EvaluationMethod.LLM_AS_JUDGE in session.request.methods:
            await self._emit(
                session,
                "evaluation_started",
                {"method": "llm_as_judge", "case_id": case.id, "trial": trial},
            )
            try:
                (
                    judge_result,
                    judge_input,
                    judge_output,
                    judge_total,
                    judge_ms,
                ) = await evaluate_with_judge(
                    self._settings, case, output, session.request.judge_role
                )
                evaluations.append(judge_result)
            except Exception as error:  # noqa: BLE001
                evaluations.append(
                    EvaluationResult(
                        method=EvaluationMethod.LLM_AS_JUDGE,
                        status="error",
                        correctness_definition=case.correctness_definition,
                        reason=f"{type(error).__name__}: {error}",
                        rubric=case.rubric,
                        threshold=case.threshold,
                    )
                )
        agent_resolved = resolve_role(self._settings, "agent")
        judge_resolved = (
            resolve_role(self._settings, session.request.judge_role)
            if EvaluationMethod.LLM_AS_JUDGE in session.request.methods
            else None
        )
        agent_cost = estimate_cost(
            model=agent.model,
            pricing_profile=session.request.pricing_profiles.get("agent", "standard"),
            input_tokens=agent.input_tokens,
            output_tokens=agent.output_tokens,
        )
        judge_cost = (
            estimate_cost(
                model=judge_resolved.model,
                pricing_profile=session.request.pricing_profiles.get("judge", "free"),
                input_tokens=judge_input,
                output_tokens=judge_output,
            )
            if judge_resolved
            else None
        )
        costs_known = agent_cost.usd is not None and (
            judge_cost is None or judge_cost.usd is not None
        )
        total_ms = round((asyncio.get_running_loop().time() - started) * 1000)
        metrics = RunMetrics(
            latency_ms=total_ms,
            input_tokens=_sum_available(agent.input_tokens, judge_input),
            output_tokens=_sum_available(agent.output_tokens, judge_output),
            total_tokens=_sum_available(agent.total_tokens, judge_total),
            cost_usd=((agent_cost.usd or 0) + ((judge_cost.usd or 0) if judge_cost else 0))
            if costs_known
            else None,
            cost_status="estimated" if costs_known else "unavailable",
            cost_source="pricing_catalog" if costs_known else "none",
            time_to_first_token_ms=agent.time_to_first_token_ms,
            generation_ms=agent.latency_ms,
            judge_ms=judge_ms or None,
            total_latency_ms=total_ms,
            cost_formula=(
                f"agente: {agent_cost.formula}; juiz: {judge_cost.formula if judge_cost else 'não selecionado'}"
                if costs_known
                else None
            ),
            pricing_version=agent_cost.catalog_version,
        )
        if EvaluationMethod.PROGRAMMATIC_CHECK in session.request.methods:
            limits = case.metric_limits
            checks = {
                "latency_ms": limits.latency_ms is None or total_ms <= limits.latency_ms,
                "total_tokens": limits.total_tokens is None
                or (
                    metrics.total_tokens is not None and metrics.total_tokens <= limits.total_tokens
                ),
                "cost_usd": limits.cost_usd is None
                or (metrics.cost_usd is not None and metrics.cost_usd <= limits.cost_usd),
            }
            is_normative = any(value is not None for value in limits.model_dump().values())
            programmatic_passed = all(checks.values()) if is_normative else None
            evaluations.append(
                EvaluationResult(
                    method=EvaluationMethod.PROGRAMMATIC_CHECK,
                    status=("passed" if programmatic_passed else "failed")
                    if is_normative
                    else "observed",
                    correctness_definition="Compara métricas reais aos limites do caso; sem limites, apenas observa.",
                    passed=programmatic_passed,
                    reason="Limites programáticos aplicados."
                    if is_normative
                    else "Métricas observadas sem limite normativo.",
                    evidence={
                        **metrics.model_dump(mode="json"),
                        "limits": limits.model_dump(mode="json"),
                        "checks": checks,
                    },
                )
            )
        normative = [item for item in evaluations if item.passed is not None]
        if any(item.passed is False for item in normative):
            verdict = FinalVerdict.FAIL
        elif normative and all(item.passed is True for item in normative):
            verdict = FinalVerdict.PASS
        else:
            verdict = FinalVerdict.INCONCLUSIVE
        run = RunVerdict(
            run_id=f"run_{uuid4().hex[:12]}",
            session_id=session.session_id,
            trial_index=trial,
            case_id=case.id,
            created_at=utc_now(),
            run_status="completed" if verdict is not FinalVerdict.INCONCLUSIVE else "partial",
            final_verdict=verdict,
            candidate_origin="live_model",
            agent_input=case.input,
            agent_output=output,
            tool_calls=list(agent.tool_calls),
            evaluations=evaluations,
            metrics=metrics,
            agent_provider=agent_resolved.provider,
            agent_model=agent_resolved.model,
            judge_provider=judge_resolved.provider if judge_resolved else None,
            judge_model=judge_resolved.model if judge_resolved else None,
            retrieved_context=[
                {"id": item.chunk.id, "text": item.chunk.text, "score": item.score}
                for item in ranked
            ],
        )
        await self._store.save_run(run.run_id, run.case_id, run.model_dump_json())
        await self._emit(
            session,
            "evaluation_completed",
            {
                "case_id": case.id,
                "trial": trial,
                "evaluations": [item.model_dump(mode="json") for item in evaluations],
            },
        )
        return run
