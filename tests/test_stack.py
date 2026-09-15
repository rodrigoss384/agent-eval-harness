import asyncio
from pathlib import Path

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.main import create_app
from src.models import CandidateInput, EvaluationMethod, RunRequest
from src.storage import SQLiteStore


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=tmp_path / "evals.db",
        static_dir=tmp_path / "missing-static",
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncClient:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready", "version": "1.0.0"}


async def test_models_endpoint_does_not_expose_keys(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "evals.db",
        static_dir=tmp_path / "static",
        openai_api_key="segredo-que-nao-pode-vazar",
        eval_agent_provider="openai",
        eval_agent_model="gpt-example",
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            response = await api.get("/api/models")

    body = response.json()
    assert response.status_code == 200
    assert body[0] == {
        "role": "agent",
        "provider": "openai",
        "model": "gpt-example",
        "configured": True,
        "base_url": "https://api.openai.com/v1",
    }
    assert "segredo-que-nao-pode-vazar" not in response.text
    assert {item["role"] for item in body} == {"agent", "judge", "judge_alt"}


async def test_spa_html_is_never_served_from_a_stale_browser_cache(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (static_dir / "agent-eval-mark.svg").write_text("<svg></svg>", encoding="utf-8")
    (static_dir / "favicon-32.png").write_bytes(b"favicon")
    (static_dir / "apple-touch-icon.png").write_bytes(b"touch-icon")
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "evals.db",
        static_dir=static_dir,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            response = await api.get("/bias")
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"
            assert response.headers["pragma"] == "no-cache"
            assert response.headers["expires"] == "0"

            for asset, content_type in (
                ("agent-eval-mark.svg", "image/svg+xml"),
                ("favicon-32.png", "image/png"),
                ("apple-touch-icon.png", "image/png"),
            ):
                asset_response = await api.get(f"/{asset}")
                assert asset_response.status_code == 200
                assert asset_response.headers["content-type"].startswith(content_type)
                assert asset_response.headers["cache-control"] == "no-cache"


async def test_dataset_exposes_representative_case(client: AsyncClient) -> None:
    response = await client.get("/api/eval/dataset")

    assert response.status_code == 200
    cases = response.json()
    assert cases[0]["id"] == "case_001"
    assert cases[0]["deterministic_rule"]["kind"] == "exact"
    assert cases[0]["correctness_definition"]


async def test_offline_run_persists_visible_rationale(client: AsyncClient) -> None:
    request = RunRequest(
        case_id="case_001",
        methods=[EvaluationMethod.DETERMINISTIC_MATCH, EvaluationMethod.PROGRAMMATIC_CHECK],
        candidate=CandidateInput(output="Brasília", latency_ms=18, input_tokens=5, output_tokens=2),
    )

    response = await client.post("/api/eval/run", json=request.model_dump(mode="json"))

    assert response.status_code == 200
    verdict = response.json()
    assert verdict["candidate_origin"] == "supplied_trace"
    assert verdict["run_status"] == "completed"
    assert verdict["final_verdict"] == "pass"
    assert verdict["evaluations"][0]["status"] == "passed"
    assert verdict["evaluations"][0]["correctness_definition"]
    assert verdict["evaluations"][1]["status"] == "observed"
    assert verdict["metrics"]["cost_usd"] is None
    assert verdict["metrics"]["cost_status"] == "unavailable"

    stored = await client.get(f"/api/eval/runs/{verdict['run_id']}")
    assert stored.status_code == 200
    assert stored.json() == verdict


async def test_deterministic_divergence_fails(client: AsyncClient) -> None:
    payload = {
        "case_id": "case_001",
        "methods": ["deterministic_match"],
        "candidate": {"output": "Rio de Janeiro", "tool_calls": []},
    }

    response = await client.post("/api/eval/run", json=payload)

    assert response.status_code == 200
    assert response.json()["final_verdict"] == "fail"


async def test_unknown_case_uses_problem_details(client: AsyncClient) -> None:
    response = await client.post(
        "/api/eval/run",
        json={
            "case_id": "case_inexistente",
            "methods": ["deterministic_match"],
            "candidate": {"output": "qualquer"},
        },
    )

    assert response.status_code == 404
    body = response.json()
    assert body["type"] == "urn:agent-eval:problem:case-not-found"
    assert body["title"] == "Caso não encontrado"
    assert body["request_id"]


async def test_live_session_without_provider_is_auditable_problem(client: AsyncClient) -> None:
    response = await client.post(
        "/api/eval/sessions",
        json={
            "mode": "single",
            "dataset_id": "builtin-v2",
            "case_ids": ["case_retrieval_advanced_001"],
            "methods": ["deterministic_match", "llm_as_judge", "programmatic_check"],
            "judge_role": "judge_alt",
            "pricing_profiles": {"agent": "standard", "judge": "free"},
            "concurrency": 2,
            "trials": 3,
        },
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Sessão live indisponível"


async def test_unknown_live_session_uses_problem_details(client: AsyncClient) -> None:
    response = await client.get("/api/eval/sessions/session_inexistente/events")

    assert response.status_code == 404
    assert response.json()["title"] == "Sessão não encontrada"


async def test_store_survives_reinitialization(settings: Settings) -> None:
    first = SQLiteStore(settings.database_path)
    await first.initialize()
    await first.save_run("run_persisted", "case_001", '{"run_id":"run_persisted"}')
    await first.close()

    second = SQLiteStore(settings.database_path)
    await second.initialize()
    stored = await second.get_run("run_persisted")
    await second.close()

    assert stored == '{"run_id":"run_persisted"}'


async def test_store_serializes_concurrent_writes(settings: Settings) -> None:
    store = SQLiteStore(settings.database_path)
    await store.initialize()

    await asyncio.gather(
        store.save_run("run_a", "case_001", '{"run_id":"run_a"}'),
        store.save_run("run_b", "case_001", '{"run_id":"run_b"}'),
    )
    documents = await store.list_runs(limit=10, offset=0)
    await store.close()

    assert {document for document in documents} == {
        '{"run_id":"run_a"}',
        '{"run_id":"run_b"}',
    }


async def test_store_rejects_invalid_json(settings: Settings) -> None:
    store = SQLiteStore(settings.database_path)
    await store.initialize()

    with pytest.raises(aiosqlite.IntegrityError):
        await store.save_run("run_invalid", "case_001", "not-json")
    await store.close()
