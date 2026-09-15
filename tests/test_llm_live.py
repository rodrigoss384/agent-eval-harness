"""Smokes reais e opt-in dos providers configurados."""

import os
from pathlib import Path

import pytest

from src.config import Settings
from src.eval.live import LiveEvaluationManager
from src.llm.factory import invoke_role
from src.models import EvaluationMethod, SessionRequest
from src.storage import SQLiteStore

pytestmark = pytest.mark.live


def _live_settings() -> Settings:
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("Defina RUN_LIVE_LLM_TESTS=1 para autorizar chamadas com custo.")
    return Settings()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["agent", "judge_alt"])
async def test_configured_provider_answers_real_request(role: str) -> None:
    settings = _live_settings()
    response = await invoke_role(
        settings,
        role,  # type: ignore[arg-type]
        "Responda somente com a palavra OK.",
    )

    assert response.text.strip()
    assert response.provider
    assert response.model
    assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_live_session_streams_three_real_trials(tmp_path: Path) -> None:
    settings = _live_settings()
    settings.database_path = tmp_path / "live-provider.db"
    settings.llm_timeout_seconds = 60
    store = SQLiteStore(settings.database_path)
    await store.initialize()
    manager = LiveEvaluationManager(settings, store)
    accepted = await manager.start(
        SessionRequest(
            case_ids=["case_retrieval_advanced_001"],
            methods=[
                EvaluationMethod.DETERMINISTIC_MATCH,
                EvaluationMethod.LLM_AS_JUDGE,
                EvaluationMethod.PROGRAMMATIC_CHECK,
            ],
            pricing_profiles={"agent": "standard", "judge": "free"},
        )
    )
    event_types = []
    async for event in manager.events(accepted.session_id, 0):
        event_types.append(event["event_type"])

    session = await manager.get(accepted.session_id)
    assert session is not None
    assert len(session.runs) == 3
    assert all(run.candidate_origin == "live_model" for run in session.runs)
    assert all(run.metrics.total_tokens for run in session.runs)
    assert "generation_token" in event_types
    assert "evaluation_completed" in event_types
    await manager.shutdown()
    await store.close()
