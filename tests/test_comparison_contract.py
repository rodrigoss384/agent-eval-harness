import json

import httpx
import pytest

from src.config import Settings
from src.dataset import find_case
from src.eval.context import evaluation_state
from src.eval.dispatch import evaluate_model
from src.eval.telemetry import combine_metrics, final_verdict, response_metrics
from src.llm.factory import RoleResponse, resolve_role
from src.llm.jev import DecisionResponse, JevContractError, request_decision
from src.models import EvaluationMethod as Method
from src.models import EvaluationMetrics, EvaluationResult, FinalVerdict


def settings():
    return Settings(
        _env_file=None,
        openai_api_key="openai-only",
        openrouter_api_key="router-only",
        gemini_api_key="google-only",
        eval_judge_provider="openai",
        eval_judge_model="gpt-4.1-mini",
        eval_judge_alt_provider="gemini",
        eval_judge_alt_model="gemini-3.1-flash-lite",
    )


def test_provider_isolation_and_cache_estimate():
    s = settings()
    assert resolve_role(s, "judge").api_key.get_secret_value() == "openai-only"
    assert resolve_role(s, "judge_alt").api_key.get_secret_value() == "google-only"
    assert resolve_role(s, "judge").base_url == "https://api.openai.com/v1"
    assert "googleapis.com" in resolve_role(s, "judge_alt").base_url
    response = RoleResponse(
        text="",
        provider="openai",
        model="gpt-4.1-mini-2025-04-14",
        latency_ms=100,
        input_tokens=1000,
        output_tokens=100,
        total_tokens=1100,
        cached_input_tokens=800,
    )
    metric = response_metrics(response)
    assert metric.cost_status == "estimated"
    assert metric.cost_usd == pytest.approx(0.00032)
    assert metric.cost_source == "pricing_catalog"
    assert metric.pricing_version


async def test_same_state_and_sibling_result_survives_failure(monkeypatch):
    case = find_case("case_001")
    state = evaluation_state(case, "Brasília")

    async def fake_llm(settings, role, prompt):
        assert state in prompt
        return RoleResponse(
            text=json.dumps(
                {
                    "score": 1,
                    "passed": True,
                    "reason": "A resposta corresponde à referência correta.",
                    "evidence": ["Brasília"],
                }
            ),
            provider="openai",
            model="gpt-4.1-mini",
            latency_ms=100,
            input_tokens=30,
            output_tokens=40,
            total_tokens=70,
        )

    async def fake_jev(settings, received):
        assert received == state
        return DecisionResponse(
            probability=1,
            model="typesafe/jev-1.13",
            metrics=EvaluationMetrics(
                input_tokens=30,
                output_tokens=0,
                total_tokens=30,
                cost_usd=0.000001,
                cost_status="reported",
                cost_source="provider_response",
            ),
        )

    monkeypatch.setattr("src.eval.judge.invoke_role", fake_llm)
    monkeypatch.setattr("src.eval.decision.request_decision", fake_jev)
    llm = await evaluate_model(settings(), case, "Brasília", Method.LLM_AS_JUDGE)
    jev = await evaluate_model(settings(), case, "Brasília", Method.DECISION_MODEL)
    assert llm.evaluated_state == jev.evaluated_state == state
    assert llm.rationale_available and not jev.rationale_available
    total = combine_metrics(None, [llm, jev], 200)
    assert total.total_tokens == 100
    assert total.cost_source == "mixed"

    async def broken(*args):
        raise httpx.ReadTimeout("test timeout")

    monkeypatch.setattr("src.eval.decision.request_decision", broken)
    failed = await evaluate_model(settings(), case, "Brasília", Method.DECISION_MODEL)
    assert failed.status == "error" and failed.passed is None
    assert final_verdict([llm, failed]) == FinalVerdict.INCONCLUSIVE
    assert combine_metrics(None, [llm, failed], 200).cost_usd is None
    assert llm.passed is True


@pytest.mark.parametrize("status", [401, 429, 500])
async def test_http_errors_are_not_retried_or_exposed(status):
    calls = []

    def fake(request):
        calls.append(request)
        return httpx.Response(status, text="private provider body")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake)) as client:
        with pytest.raises(JevContractError) as error:
            await request_decision(settings(), "test", client=client)
    assert len(calls) == 1
    assert "private" not in str(error.value)


def test_old_evaluation_without_metrics_still_loads():
    old = EvaluationResult.model_validate(
        {
            "method": "llm_as_judge",
            "status": "passed",
            "passed": True,
            "reason": "old",
            "correctness_definition": "old",
        }
    )
    assert old.metrics is None
    assert old.score_type is None


async def test_supplied_run_preserves_candidate_metrics_and_other_judge(tmp_path, monkeypatch):
    from src.eval.runner import run_evaluation
    from src.models import CandidateInput, RunRequest
    from src.storage import SQLiteStore

    async def fake(settings, case, output, method):
        return EvaluationResult(
            method=method,
            status="passed",
            passed=True,
            reason="test",
            correctness_definition=case.correctness_definition,
            metrics=EvaluationMetrics(
                input_tokens=20,
                output_tokens=0,
                total_tokens=20,
                latency_ms=50,
                cost_usd=0.0001,
                cost_status="reported",
                cost_source="provider_response",
            ),
        )

    monkeypatch.setattr("src.eval.runner.evaluate_model", fake)
    store = SQLiteStore(tmp_path / "provided.db")
    await store.initialize()
    try:
        result = await run_evaluation(
            RunRequest(
                case_id="case_001",
                methods=[Method.DECISION_MODEL],
                candidate=CandidateInput(
                    output="Brasília",
                    input_tokens=100,
                    output_tokens=10,
                    cost_usd=0.001,
                    latency_ms=200,
                ),
            ),
            store,
        )
        assert result.metrics.agent_metrics.input_tokens == 100
        assert result.metrics.total_tokens == 130
        assert result.metrics.cost_usd == pytest.approx(0.0011)
    finally:
        await store.close()


async def test_llm_captures_provider_response_id_model_and_usage(monkeypatch):
    from langchain_core.messages import AIMessage

    from src.llm.factory import invoke_role

    class FakeModel:
        async def ainvoke(self, messages):
            return AIMessage(
                content="test",
                id="lc_run-local",
                response_metadata={
                    "id": "chatcmpl-provider",
                    "model_name": "gpt-4.1-mini-2025-04-14",
                },
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "input_token_details": {"cache_read": 50},
                },
            )

    monkeypatch.setattr("src.llm.factory.create_chat_model", lambda *args: FakeModel())
    result = await invoke_role(settings(), "judge", "test")
    assert result.request_id == "chatcmpl-provider"
    assert result.model == "gpt-4.1-mini-2025-04-14"
    assert result.cached_input_tokens == 50
    assert result.queue_ms >= 0
