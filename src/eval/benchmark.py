"""Benchmark pareado, sequencial e com orçamento reservado antes de cada chamada."""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
from contextlib import suppress
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.config import PROVIDER_BASE_URLS, Settings
from src.dataset import load_dataset
from src.eval.benchmark_models import (
    Benchmark,
    BenchmarkAccepted,
    BenchmarkCall,
    BenchmarkRequest,
    BenchmarkSample,
    BenchmarkTrial,
)
from src.eval.context import DECISION_QUESTION, evaluation_state, judge_prompt
from src.eval.dispatch import candidate_output, evaluate_model
from src.eval.pricing import _catalog
from src.llm.factory import resolve_role
from src.llm.jev import jev_key
from src.models import CandidateInput, EvaluationMethod, utc_now
from src.storage import SQLiteStore

CANDIDATES_PATH = Path(__file__).resolve().parents[2] / "data/benchmark_candidates_v1.json"
EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "data/benchmark_example.json"
METHODS = (EvaluationMethod.LLM_AS_JUDGE, EvaluationMethod.DECISION_MODEL)
TERMINAL = {"completed", "partial", "failed", "cancelled", "interrupted", "budget_exhausted"}


class BenchmarkError(ValueError):
    """Erro público de configuração ou orçamento."""


def load_samples() -> list[BenchmarkSample]:
    cases = {case.id: case for case in load_dataset()}
    data = json.loads(CANDIDATES_PATH.read_text())
    return [
        BenchmarkSample(
            case=cases[row["case_id"]], **{k: v for k, v in row.items() if k != "case_id"}
        )
        for row in data["candidates"]
    ]


def sample_output(sample: BenchmarkSample) -> str:
    return candidate_output(CandidateInput(output=sample.output, tool_calls=sample.tool_calls))


def pricing_snapshot(settings: Settings) -> dict[str, Any]:
    catalog = _catalog()
    prices = {}
    for method, model in (
        ("llm_as_judge", settings.eval_judge_model),
        ("decision_model", settings.jev_model),
    ):
        entry = catalog["models"].get(model, {}).get("standard")
        if not entry or not entry.get("verified_at"):
            raise BenchmarkError("O benchmark exige tarifas verificadas no catálogo de preços.")
        prices[method] = dict(entry)
    return {"version": catalog["version"], "prices": prices}


def reserve_cost(
    sample: BenchmarkSample, method: EvaluationMethod, pricing: dict[str, Any]
) -> float:
    output = sample_output(sample)
    prompt = (
        judge_prompt(sample.case, output)
        if method == METHODS[0]
        else (evaluation_state(sample.case, output) + DECISION_QUESTION)
    )
    # UTF-8 bytes is a conservative token bound for these text tokenizers. Extra room
    # covers protocol framing. No context truncation or discounted caching is assumed.
    input_bound = len(prompt.encode("utf-8")) + 1024
    if input_bound > 32_000:
        raise BenchmarkError("Contexto excede o limite conservador do benchmark; não foi truncado.")
    rate = pricing["prices"][method]
    output_bound = 800 if method == METHODS[0] else 0
    value = (
        Decimal(input_bound) * Decimal(str(rate["input_per_million_usd"]))
        + Decimal(output_bound) * Decimal(str(rate["output_per_million_usd"]))
    ) / Decimal(1_000_000)
    return float(value)


class BenchmarkManager:
    def __init__(self, settings: Settings, store: SQLiteStore):
        self.settings = settings
        self.store = store
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.lock = asyncio.Lock()
        self.stopping = False

    async def initialize(self) -> None:
        db = self.store._ready_connection()
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                benchmark_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                created_at TEXT NOT NULL, document TEXT NOT NULL CHECK(json_valid(document))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_benchmark ON benchmarks((1))
                WHERE status IN ('queued', 'running');
            CREATE TABLE IF NOT EXISTS benchmark_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_id TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload))
            );
            CREATE INDEX IF NOT EXISTS benchmark_event_cursor
                ON benchmark_events(benchmark_id, event_id);
            INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                VALUES(4, CURRENT_TIMESTAMP);
        """)
        await db.commit()
        for item in await self.list(limit=10000):
            if item.status in {"queued", "running"}:
                item.status = "interrupted"
                item.error = (
                    "Serviço reiniciado. Reservas incertas preservadas; nenhuma chamada repetida."
                )
                for call in item.calls:
                    if call.status == "reserved":
                        call.status = "interrupted"
                await self._save(item)

    async def _save(self, benchmark: Benchmark) -> None:
        benchmark.updated_at = utc_now()
        db = self.store._ready_connection()
        async with self.store._write_lock:
            try:
                await db.execute(
                    """INSERT INTO benchmarks VALUES(?,?,?,?)
                    ON CONFLICT(benchmark_id) DO UPDATE SET
                    status=excluded.status, document=excluded.document""",
                    (
                        benchmark.benchmark_id,
                        benchmark.status,
                        benchmark.created_at.isoformat(),
                        benchmark.model_dump_json(),
                    ),
                )
                await db.execute(
                    "INSERT INTO benchmark_events(benchmark_id,payload) VALUES(?,?)",
                    (
                        benchmark.benchmark_id,
                        json.dumps(
                            {
                                "status": benchmark.status,
                                "calls_attempted": len(benchmark.calls),
                                "accounted_usd": benchmark.accounted_usd,
                                "updated_at": benchmark.updated_at.isoformat(),
                            }
                        ),
                    ),
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def get(self, benchmark_id: str) -> Benchmark | None:
        async with self.store._ready_connection().execute(
            "SELECT document FROM benchmarks WHERE benchmark_id=?", (benchmark_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return Benchmark.model_validate_json(row[0]) if row else None

    async def list(self, limit: int = 50, offset: int = 0) -> list[Benchmark]:
        async with self.store._ready_connection().execute(
            "SELECT document FROM benchmarks ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
        return [Benchmark.model_validate_json(row[0]) for row in rows]

    async def events(self, benchmark_id: str, after: int) -> builtins.list[dict[str, Any]]:
        async with self.store._ready_connection().execute(
            (
                "SELECT event_id,payload FROM benchmark_events WHERE "
                "benchmark_id=? AND event_id>? ORDER BY event_id"
            ),
            (benchmark_id, after),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"event_id": row[0], "payload": json.loads(row[1])} for row in rows]

    def preflight(self) -> dict[str, Any]:
        issues = []
        try:
            jev_key(self.settings)
            jev_ready = True
        except ValueError:
            jev_ready = False
        try:
            role = resolve_role(self.settings, "judge")
            if role.provider != "openai" or role.model != "gpt-4.1-mini":
                issues.append(
                    "O benchmark v1 usa EVAL_JUDGE_PROVIDER=openai e EVAL_JUDGE_MODEL=gpt-4.1-mini."
                )
            if role.base_url.rstrip("/") != PROVIDER_BASE_URLS["openai"]:
                issues.append("O benchmark usa o endpoint oficial direto da OpenAI.")
            jev_key(self.settings)
            if self.settings.jev_base_url != "https://openrouter.ai/api/alpha/decisions":
                issues.append("O benchmark v1 usa a API Decisions oficial do OpenRouter.")
            if self.settings.jev_model != "typesafe/jev-1.13":
                issues.append("O benchmark v1 está versionado para typesafe/jev-1.13.")
            pricing = pricing_snapshot(self.settings)
        except ValueError as error:
            issues.append(str(error))
            pricing = {}
        return {
            "ready": not issues,
            "jev_ready": jev_ready,
            "issues": issues,
            "pricing": pricing,
            "calls_planned": 288,
            "max_calls": 300,
            "max_cost_usd": 2,
            "models": {
                "llm_as_judge": {"provider": "openai", "model": self.settings.eval_judge_model},
                "decision_model": {"provider": "openrouter", "model": self.settings.jev_model},
            },
            "trials": 3,
            "candidates": 48,
            "cases": 24,
        }

    async def start(self, request: BenchmarkRequest) -> BenchmarkAccepted:
        async with self.lock:
            preflight = self.preflight()
            if not preflight["ready"]:
                raise BenchmarkError(" ".join(preflight["issues"]))
            if any(item.status not in TERMINAL for item in await self.list()):
                raise BenchmarkError("Já existe um benchmark em andamento.")
            samples = load_samples()
            if request.case_ids is not None:
                known = {s.case.id for s in samples}
                if set(request.case_ids) - known:
                    raise BenchmarkError("Caso ausente do benchmark versionado.")
                samples = [s for s in samples if s.case.id in request.case_ids]
            checksum = hashlib.sha256(
                json.dumps(
                    [s.model_dump(mode="json") for s in samples], ensure_ascii=False, sort_keys=True
                ).encode()
            ).hexdigest()
            item = Benchmark(
                benchmark_id="benchmark_" + uuid4().hex[:12],
                request=request,
                dataset_checksum=checksum,
                samples=samples,
                calls_planned=len(samples) * 3 * 2,
                configuration={
                    "models": preflight["models"],
                    "pricing": preflight["pricing"],
                    "llm_temperature": 0,
                    "llm_max_output_tokens": 800,
                    "decision_question": DECISION_QUESTION,
                    "order": "alternating-sequential-v1",
                    "trials_per_candidate": 3,
                    "threshold_policy": "original-case",
                    "candidate_origin": "supplied_trace",
                },
            )
            await self._save(item)
            self.tasks[item.benchmark_id] = asyncio.create_task(self._execute(item))
            return BenchmarkAccepted(
                benchmark_id=item.benchmark_id,
                status="queued",
                calls_planned=item.calls_planned,
                events_url=f"/api/eval/benchmarks/{item.benchmark_id}/events",
            )

    async def _execute(self, benchmark: Benchmark) -> None:
        try:
            consecutive_errors = dict.fromkeys(METHODS, 0)
            benchmark.status = "running"
            await self._save(benchmark)
            for index, sample in enumerate(benchmark.samples):
                for trial in range(1, 4):
                    run = BenchmarkTrial(sample_id=sample.id, trial_index=trial)
                    benchmark.runs.append(run)
                    order = METHODS if (index * 3 + trial) % 2 else tuple(reversed(METHODS))
                    for method in order:
                        reserve = reserve_cost(sample, method, benchmark.configuration["pricing"])
                        if len(benchmark.calls) >= benchmark.request.max_calls or Decimal(
                            str(benchmark.accounted_usd)
                        ) + Decimal(str(reserve)) > Decimal(str(benchmark.request.max_cost_usd)):
                            benchmark.status = "budget_exhausted"
                            benchmark.error = (
                                "Limite atingido antes da próxima chamada; resultados parciais "
                                "preservados."
                            )
                            await self._save(benchmark)
                            return
                        call = BenchmarkCall(
                            sample_id=sample.id,
                            trial_index=trial,
                            method=method,
                            reserved_usd=reserve,
                            accounted_usd=reserve,
                        )
                        benchmark.calls.append(call)
                        benchmark.accounted_usd = sum(c.accounted_usd for c in benchmark.calls)
                        await self._save(benchmark)
                        result = await evaluate_model(
                            self.settings,
                            sample.case,
                            sample_output(sample),
                            method,
                            "judge",
                            "standard",
                        )
                        call.result = result
                        call.completed_at = utc_now()
                        call.status = "completed" if result.passed is not None else "error"
                        if result.metrics and result.metrics.cost_usd is not None:
                            call.accounted_usd = result.metrics.cost_usd
                            call.accounting = (
                                "reported"
                                if result.metrics.cost_status == "reported"
                                else "estimated"
                            )
                        benchmark.accounted_usd = sum(c.accounted_usd for c in benchmark.calls)
                        run.evaluations.append(result)
                        await self._save(benchmark)
                        consecutive_errors[method] = (
                            consecutive_errors[method] + 1 if call.status == "error" else 0
                        )
                        if consecutive_errors[method] >= 3:
                            benchmark.status = "partial"
                            benchmark.error = (
                                "Três erros consecutivos do mesmo juiz; novas chamadas suspensas. "
                                "Resultados e reservas incertas preservados."
                            )
                            await self._save(benchmark)
                            return
                        if call.accounted_usd > reserve:
                            benchmark.status = "partial"
                            benchmark.error = (
                                "Consumo excedeu a reserva conservadora; execução interrompida "
                                "para revisão tarifária."
                            )
                            await self._save(benchmark)
                            return
            benchmark.status = (
                "partial" if any(c.status == "error" for c in benchmark.calls) else "completed"
            )
        except asyncio.CancelledError:
            benchmark.status = "interrupted" if self.stopping else "cancelled"
            benchmark.error = "Execução interrompida; reservas de chamadas incertas preservadas."
            for call in benchmark.calls:
                if call.status == "reserved":
                    call.status = "interrupted"
            await self._save(benchmark)
            raise
        except Exception as error:
            benchmark.status = "failed"
            benchmark.error = (
                f"{type(error).__name__}: benchmark interrompido; reservas preservadas."
            )
        finally:
            await self._save(benchmark)

    async def wait(self, benchmark_id: str) -> None:
        task = self.tasks.get(benchmark_id)
        if task:
            await task

    async def cancel(self, benchmark_id: str) -> Benchmark:
        item = await self.get(benchmark_id)
        if item is None:
            raise BenchmarkError("Benchmark não encontrado.")
        task = self.tasks.get(benchmark_id)
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        item = await self.get(benchmark_id) or item
        # A task cancelled before its first instruction never enters its finally block.
        if item.status not in TERMINAL:
            item.status = "cancelled"
            for call in item.calls:
                if call.status == "reserved":
                    call.status = "interrupted"
            await self._save(item)
        return item

    async def shutdown(self) -> None:
        self.stopping = True
        tasks = [task for task in self.tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
