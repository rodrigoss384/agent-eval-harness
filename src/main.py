"""Aplicação FastAPI do agent-eval-harness."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.config import Settings
from src.dataset import load_dataset
from src.eval.bias import BiasAuditError, BiasAuditManager, BiasExperiment
from src.eval.datasets import DatasetValidationError, get_dataset, list_datasets, parse_import
from src.eval.live import LiveEvaluationManager, LiveSessionError, LiveSessionNotFoundError
from src.eval.runner import CaseNotFoundError, run_evaluation
from src.eval.summary import summarize_session
from src.models import (
    BiasAudit,
    BiasAuditAccepted,
    BiasAuditRequest,
    DatasetDocument,
    DatasetImportRequest,
    DatasetMetadata,
    EvaluationSession,
    HealthResponse,
    ModelRoleStatus,
    RunRequest,
    RunVerdict,
    SessionAccepted,
    SessionRequest,
    SessionSummary,
)
from src.storage import SQLiteStore


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria a aplicação com dependências isoláveis por processo de teste."""
    resolved_settings = settings or Settings()
    store = SQLiteStore(resolved_settings.database_path)
    live_manager = LiveEvaluationManager(resolved_settings, store)
    bias_manager = BiasAuditManager(resolved_settings, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await store.initialize()
        await store.mark_running_sessions_interrupted()
        await store.mark_running_bias_audits_interrupted()
        yield
        await live_manager.shutdown()
        await bias_manager.shutdown()
        await store.close()

    app = FastAPI(
        title="agent-eval-harness",
        summary="Avaliação de agentes com racional auditável.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.store = store
    app.state.live_manager = live_manager
    app.state.bias_manager = bias_manager

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("x-request-id", uuid4().hex)
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    @app.exception_handler(CaseNotFoundError)
    async def case_not_found_handler(request: Request, _: CaseNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            media_type="application/problem+json",
            content={
                "type": "urn:agent-eval:problem:case-not-found",
                "title": "Caso não encontrado",
                "status": 404,
                "detail": "O caso informado não existe no dataset sintético.",
                "instance": str(request.url.path),
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(LiveSessionError)
    async def live_session_handler(request: Request, error: LiveSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            media_type="application/problem+json",
            content={
                "type": "urn:agent-eval:problem:live-session",
                "title": "Sessão live indisponível",
                "status": 409,
                "detail": str(error),
                "instance": str(request.url.path),
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(LiveSessionNotFoundError)
    async def live_session_not_found_handler(
        request: Request, error: LiveSessionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            media_type="application/problem+json",
            content={
                "type": "urn:agent-eval:problem:session-not-found",
                "title": "Sessão não encontrada",
                "status": 404,
                "detail": str(error),
                "instance": str(request.url.path),
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(DatasetValidationError)
    async def dataset_validation_handler(
        request: Request, error: DatasetValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "urn:agent-eval:problem:dataset-invalid",
                "title": "Dataset inválido",
                "status": 422,
                "detail": str(error),
                "errors": error.errors,
                "instance": str(request.url.path),
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(BiasAuditError)
    async def bias_audit_handler(request: Request, error: BiasAuditError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            media_type="application/problem+json",
            content={
                "type": "urn:agent-eval:problem:bias-audit",
                "title": "Auditoria indisponível",
                "status": 409,
                "detail": str(error),
                "instance": str(request.url.path),
                "request_id": request.state.request_id,
            },
        )

    @app.get("/api/health")
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/models")
    async def models() -> list[ModelRoleStatus]:
        roles: list[tuple[str, str | None, str | None]] = [
            ("agent", resolved_settings.eval_agent_provider, resolved_settings.eval_agent_model),
            ("judge", resolved_settings.eval_judge_provider, resolved_settings.eval_judge_model),
            (
                "judge_alt",
                resolved_settings.eval_judge_alt_provider,
                resolved_settings.eval_judge_alt_model,
            ),
        ]
        return [
            ModelRoleStatus(
                role=role,  # type: ignore[arg-type]
                provider=provider,
                model=model,
                configured=bool(provider and model and resolved_settings.api_key_for(provider)),
                base_url=resolved_settings.base_url_for(provider),
            )
            for role, provider, model in roles
        ]

    @app.get("/api/eval/dataset")
    async def dataset():  # type: ignore[no-untyped-def]
        return load_dataset()

    @app.get("/api/eval/datasets")
    async def datasets() -> list[DatasetMetadata]:
        return await list_datasets(store)

    @app.get("/api/eval/datasets/{dataset_id}")
    async def dataset_detail(dataset_id: str, request: Request):  # type: ignore[no-untyped-def]
        document = await get_dataset(store, dataset_id)
        if document is None:
            return JSONResponse(
                status_code=404,
                media_type="application/problem+json",
                content={
                    "type": "urn:agent-eval:problem:dataset-not-found",
                    "title": "Dataset não encontrado",
                    "status": 404,
                    "detail": "O dataset informado não existe.",
                    "instance": str(request.url.path),
                    "request_id": request.state.request_id,
                },
            )
        return document

    @app.post("/api/eval/datasets/import", status_code=201)
    async def import_dataset(request: DatasetImportRequest) -> DatasetDocument:
        document = parse_import(request)
        await store.save_dataset(
            document.metadata.dataset_id,
            document.metadata.checksum,
            document.model_dump_json(),
        )
        return document

    @app.post("/api/eval/run")
    async def evaluate(request: RunRequest) -> RunVerdict:
        return await run_evaluation(request, store)

    @app.get("/api/eval/runs")
    async def list_runs(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[RunVerdict]:
        documents = await store.list_runs(limit, offset)
        return [RunVerdict.model_validate_json(document) for document in documents]

    @app.get("/api/eval/runs/{run_id}")
    async def get_run(run_id: str, request: Request):  # type: ignore[no-untyped-def]
        document = await store.get_run(run_id)
        if document is None:
            return JSONResponse(
                status_code=404,
                media_type="application/problem+json",
                content={
                    "type": "urn:agent-eval:problem:run-not-found",
                    "title": "Run não encontrado",
                    "status": 404,
                    "detail": "O run informado não existe no histórico local.",
                    "instance": str(request.url.path),
                    "request_id": request.state.request_id,
                },
            )
        return RunVerdict.model_validate_json(document)

    @app.post("/api/eval/sessions", status_code=202)
    async def create_session(request: SessionRequest) -> SessionAccepted:
        """Persiste e inicia uma avaliação real com três tentativas."""
        return await live_manager.start(request)

    @app.get("/api/eval/sessions")
    async def list_sessions(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> list[EvaluationSession]:
        return await live_manager.list(limit, offset)

    @app.get("/api/eval/sessions/{session_id}")
    async def get_session(session_id: str, request: Request):  # type: ignore[no-untyped-def]
        session = await live_manager.get(session_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                media_type="application/problem+json",
                content={
                    "type": "urn:agent-eval:problem:session-not-found",
                    "title": "Sessão não encontrada",
                    "status": 404,
                    "detail": "A sessão informada não existe no histórico local.",
                    "instance": str(request.url.path),
                    "request_id": request.state.request_id,
                },
            )
        return session

    @app.get("/api/eval/sessions/{session_id}/summary")
    async def session_summary(session_id: str) -> SessionSummary:
        session = await live_manager.get(session_id)
        if session is None:
            raise LiveSessionNotFoundError("Sessão não encontrada.")
        return summarize_session(session)

    @app.post("/api/eval/sessions/{session_id}/cancel")
    async def cancel_session(session_id: str) -> EvaluationSession:
        return await live_manager.cancel(session_id)

    @app.get("/api/eval/sessions/{session_id}/events")
    async def session_events(session_id: str, request: Request) -> StreamingResponse:
        """Transmite marcos persistidos e tokens efêmeros no formato SSE."""
        session = await live_manager.get(session_id)
        if session is None:
            raise LiveSessionNotFoundError("Sessão não encontrada.")
        header = request.headers.get("last-event-id", "0")
        try:
            after = max(0, int(header))
        except ValueError:
            after = 0

        async def stream() -> AsyncIterator[str]:
            async for event in live_manager.events(session_id, after):
                event_id = event.get("event_id")
                if event_id is not None:
                    yield f"id: {event_id}\n"
                yield f"event: {event['event_type']}\n"
                yield f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def start_bias(
        experiment: BiasExperiment, request: BiasAuditRequest
    ) -> BiasAuditAccepted:
        return await bias_manager.start(experiment, request)

    @app.post("/api/eval/bias/position", status_code=202)
    async def bias_position(request: BiasAuditRequest) -> BiasAuditAccepted:
        return await start_bias("position", request)

    @app.post("/api/eval/bias/self-preference", status_code=202)
    async def bias_self_preference(request: BiasAuditRequest) -> BiasAuditAccepted:
        return await start_bias("self_preference", request)

    @app.post("/api/eval/bias/verbosity", status_code=202)
    async def bias_verbosity(request: BiasAuditRequest) -> BiasAuditAccepted:
        return await start_bias("verbosity", request)

    @app.post("/api/eval/bias/correctness-definition", status_code=202)
    async def bias_correctness_definition(request: BiasAuditRequest) -> BiasAuditAccepted:
        return await start_bias("correctness_definition", request)

    @app.get("/api/eval/bias")
    async def list_bias(
        limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0)
    ) -> list[BiasAudit]:
        return await bias_manager.list(limit, offset)

    @app.get("/api/eval/bias/{audit_id}")
    async def get_bias(audit_id: str, request: Request):  # type: ignore[no-untyped-def]
        audit = await bias_manager.get(audit_id)
        if audit is None:
            return JSONResponse(
                status_code=404,
                media_type="application/problem+json",
                content={
                    "type": "urn:agent-eval:problem:bias-not-found",
                    "title": "Auditoria não encontrada",
                    "status": 404,
                    "detail": "A auditoria informada não existe.",
                    "instance": str(request.url.path),
                    "request_id": request.state.request_id,
                },
            )
        return audit

    @app.get("/api/eval/bias/{audit_id}/events")
    async def bias_events(audit_id: str, request: Request) -> StreamingResponse:
        header = request.headers.get("last-event-id", "0")
        try:
            after = max(0, int(header))
        except ValueError:
            after = 0

        async def stream_bias() -> AsyncIterator[str]:
            async for event in bias_manager.events(audit_id, after):
                event_id = event.get("event_id")
                if event_id is not None:
                    yield f"id: {event_id}\n"
                yield f"event: {event['event_type']}\n"
                yield f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"

        return StreamingResponse(
            stream_bias(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    static_dir = resolved_settings.static_dir.resolve()
    assets_dir = static_dir / "assets"
    index_file = static_dir / "index.html"
    if assets_dir.is_dir() and index_file.is_file():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        async def frontend_brand_asset(request: Request) -> FileResponse:
            """Entrega arquivos de marca localizados na raiz do build Vite."""
            asset_file = static_dir / request.url.path.removeprefix("/")
            return FileResponse(asset_file, headers={"Cache-Control": "no-cache"})

        for brand_asset in ("agent-eval-mark.svg", "favicon-32.png", "apple-touch-icon.png"):
            asset_file = static_dir / brand_asset
            if asset_file.is_file():
                app.add_api_route(
                    f"/{brand_asset}",
                    frontend_brand_asset,
                    methods=["GET"],
                    include_in_schema=False,
                    name=f"frontend-{brand_asset}",
                )

        @app.get("/{frontend_path:path}", include_in_schema=False)
        async def frontend(frontend_path: str) -> FileResponse:
            """Entrega o shell SPA para rotas conhecidas pelo frontend."""
            return FileResponse(
                index_file,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

    return app


app = create_app()
