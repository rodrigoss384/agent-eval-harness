"""API aditiva para benchmarks e evidência registrada."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from src.eval.benchmark import (
    EXAMPLE_PATH,
    TERMINAL,
    BenchmarkError,
    BenchmarkManager,
    load_samples,
)
from src.eval.benchmark_models import (
    Benchmark,
    BenchmarkAccepted,
    BenchmarkRequest,
    BenchmarkSample,
)
from src.eval.benchmark_stats import summarize_benchmark


def benchmark_router(manager: BenchmarkManager) -> APIRouter:
    router = APIRouter(prefix="/api/eval/benchmarks", tags=["comparação"])

    @router.get("/preflight")
    async def preflight() -> dict[str, Any]:
        return manager.preflight()

    @router.get("/samples")
    async def samples() -> list[BenchmarkSample]:
        return load_samples()

    @router.get("/example")
    async def example() -> Benchmark:
        if not EXAMPLE_PATH.exists():
            raise HTTPException(
                404, "Nenhuma comparação real registrada está incluída nesta instalação."
            )
        item = Benchmark.model_validate_json(EXAMPLE_PATH.read_text())
        item.recorded = True
        return item

    @router.post("", status_code=202)
    async def create(request: BenchmarkRequest) -> BenchmarkAccepted:
        try:
            return await manager.start(request)
        except BenchmarkError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("")
    async def listing(
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
    ) -> list[dict[str, Any]]:
        return [
            {
                "benchmark_id": b.benchmark_id,
                "created_at": b.created_at,
                "status": b.status,
                "calls_planned": b.calls_planned,
                "calls_attempted": len(b.calls),
                "accounted_usd": b.accounted_usd,
                "distinct_cases": len({s.case.id for s in b.samples}),
            }
            for b in await manager.list(limit, offset)
        ]

    async def require(benchmark_id: str) -> Benchmark:
        if benchmark_id == "example":
            return await example()
        result = await manager.get(benchmark_id)
        if result is None:
            raise HTTPException(404, "Benchmark não encontrado.")
        return result

    @router.get("/{benchmark_id}")
    async def detail(benchmark_id: str) -> Benchmark:
        return await require(benchmark_id)

    @router.get("/{benchmark_id}/summary")
    async def summary(
        benchmark_id: str, threshold: float | None = Query(None, ge=0, le=1)
    ) -> dict[str, Any]:
        return summarize_benchmark(await require(benchmark_id), threshold)

    @router.post("/{benchmark_id}/cancel")
    async def cancel(benchmark_id: str) -> Benchmark:
        await require(benchmark_id)
        if benchmark_id == "example":
            raise HTTPException(409, "Exemplo histórico somente para leitura.")
        return await manager.cancel(benchmark_id)

    @router.get("/{benchmark_id}/events")
    async def events(benchmark_id: str, request: Request) -> StreamingResponse:
        await require(benchmark_id)

        async def stream() -> AsyncIterator[str]:
            raw = request.headers.get("last-event-id", "0")
            cursor = int(raw) if raw.isdigit() else 0
            while not await request.is_disconnected():
                for event in await manager.events(benchmark_id, cursor):
                    cursor = event["event_id"]
                    yield f"id: {cursor}\nevent: progress\ndata: {json.dumps(event['payload'])}\n\n"
                item = await require(benchmark_id)
                yield f"event: snapshot\ndata: {item.model_dump_json()}\n\n"
                if item.status in TERMINAL:
                    break
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
