import asyncio

from src.config import Settings
from src.eval.live import LiveEvaluationManager
from src.eval.summary import summarize_session
from src.llm.factory import RoleResponse
from src.models import EvaluationMethod, EvaluationMetrics, EvaluationResult, SessionRequest
from src.storage import SQLiteStore


async def test_live_preserves_three_trials_and_partial_judge_results(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        openai_api_key="fake",
        openrouter_api_key="fake",
        eval_agent_provider="openai",
        eval_agent_model="gpt-4.1-mini",
        eval_judge_provider="openai",
        eval_judge_model="gpt-4.1-mini",
    )
    store = SQLiteStore(tmp_path / "live.db")
    await store.initialize()
    manager = LiveEvaluationManager(settings, store)
    received = []

    async def agent(*args):
        return RoleResponse(
            text="Brasília",
            provider="openai",
            model="gpt-4.1-mini",
            latency_ms=100,
            input_tokens=10,
            output_tokens=2,
            total_tokens=12,
        )

    async def judge(settings, case, output, method, *args):
        received.append((method, output))
        failed = method == EvaluationMethod.DECISION_MODEL
        return EvaluationResult(
            method=method,
            status="error" if failed else "passed",
            passed=None if failed else True,
            score=None if failed else 1,
            correctness_definition=case.correctness_definition,
            reason="test",
            metrics=EvaluationMetrics()
            if failed
            else EvaluationMetrics(
                input_tokens=5,
                output_tokens=2,
                total_tokens=7,
                cost_usd=0.0001,
                cost_status="reported",
                cost_source="provider_response",
            ),
        )

    monkeypatch.setattr("src.eval.live.stream_role", agent)
    monkeypatch.setattr("src.eval.live.evaluate_model", judge)
    try:
        accepted = await manager.start(
            SessionRequest(
                case_ids=["case_001"],
                judge_role="judge",
                methods=[EvaluationMethod.LLM_AS_JUDGE, EvaluationMethod.DECISION_MODEL],
            )
        )
        assert accepted.calls_planned == 9
        task = manager._tasks[accepted.session_id]
        await asyncio.wait_for(task, timeout=5)
        session = await manager.get(accepted.session_id)
        assert session.status == "partial"
        assert str(session.final_verdict) == "inconclusive"
        assert len(session.runs) == 3
        assert len(received) == 6
        assert {output for _, output in received} == {"Brasília"}
        assert all(run.evaluations[0].passed for run in session.runs)
        summary = summarize_session(session)
        assert summary.methods["decision_model"]["errors"] == 3
        assert summary.comparison["unpaired_trials"] == 3
    finally:
        await manager.shutdown()
        await store.close()


async def test_legacy_gemini_profile_and_openai_default_with_paid_override(tmp_path, monkeypatch):
    observed = []

    async def agent(*args):
        return RoleResponse(
            text="Brasília",
            provider="openai",
            model="gpt-4.1-mini",
            latency_ms=10,
            input_tokens=10,
            output_tokens=2,
            total_tokens=12,
        )

    async def judge(settings, case, output, method, role, profile):
        observed.append(profile)
        return EvaluationResult(
            method=method,
            status="passed",
            passed=True,
            score=1,
            reason="test",
            correctness_definition=case.correctness_definition,
        )

    monkeypatch.setattr("src.eval.live.stream_role", agent)
    monkeypatch.setattr("src.eval.live.evaluate_model", judge)
    for provider, profiles, expected in [
        ("gemini", {}, "free"),
        ("openai", {}, "standard"),
        ("gemini", {"judge": "paid_standard"}, "paid_standard"),
    ]:
        store = SQLiteStore(tmp_path / f"{provider}-{expected}.db")
        await store.initialize()
        manager = LiveEvaluationManager(
            Settings(
                _env_file=None,
                openai_api_key="fake",
                gemini_api_key="fake",
                eval_agent_provider="openai",
                eval_agent_model="gpt-4.1-mini",
                eval_judge_alt_provider=provider,
                eval_judge_alt_model="gemini-3.1-flash-lite"
                if provider == "gemini"
                else "gpt-4.1-mini",
            ),
            store,
        )
        try:
            accepted = await manager.start(
                SessionRequest(
                    case_ids=["case_001"],
                    judge_role="judge_alt",
                    pricing_profiles=profiles,
                    methods=[EvaluationMethod.LLM_AS_JUDGE],
                )
            )
            await manager._tasks[accepted.session_id]
            assert observed[-3:] == [expected] * 3
        finally:
            await manager.shutdown()
            await store.close()
