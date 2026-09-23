import json

import httpx
import pytest

from src.config import Settings
from src.dataset import find_case
from src.eval.decision import evaluate_with_decision_model
from src.llm.jev import JevContractError, request_decision


def configured(**kwargs):
    return Settings(_env_file=None, openrouter_api_key="router-secret", **kwargs)


async def test_decisions_contract_and_usage():
    async def handle(request):
        assert request.url == "https://openrouter.ai/api/alpha/decisions"
        assert request.headers["authorization"] == "Bearer router-secret"
        body = json.loads(request.content)
        assert body["model"] == "typesafe/jev-1.13"
        assert body["questions"]["passed"]["type"] == "noul"
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "id": "decision-test",
                "provider": "TypeSafe",
                "answers": {"passed": {"type": "noul", "noul": 0.97}},
                "usage": {"input_tokens": 100, "output_tokens": 0, "cost": 0.0000042},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        response = await request_decision(configured(jev_api_key=""), "context", client=client)
    assert response.probability == 0.97
    assert response.metrics.input_tokens == 100
    assert response.metrics.output_tokens == 0
    assert response.metrics.cost_status == "reported"
    assert response.request_id == "decision-test"


@pytest.mark.parametrize("probability", [-0.01, 1.01, True, "0.97", None, float("nan")])
async def test_rejects_invalid_probability(probability):
    async def handle(request):
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "model": "typesafe/jev-1.13",
                    "answers": {"passed": {"type": "noul", "noul": probability}},
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                }
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(JevContractError):
            await request_decision(configured(), "context", client=client)


async def test_override_key_and_custom_endpoint():
    async def handle(request):
        assert request.headers["authorization"] == "Bearer jev-only"
        assert str(request.url) == "https://example.test/decision"
        return httpx.Response(
            200,
            json={
                "model": "custom",
                "answers": {"passed": {"type": "noul", "noul": 1}},
                "usage": {"input_tokens": 3, "output_tokens": 0},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await request_decision(
            configured(
                jev_api_key="jev-only",
                jev_base_url="https://example.test/decision",
                jev_model="custom",
            ),
            "context",
            client=client,
        )
    assert result.metrics.cost_usd is None


@pytest.mark.parametrize("probability,passed", [(1, True), (0.999, False)])
async def test_threshold_and_honest_reason(monkeypatch, probability, passed):
    from src.llm.jev import DecisionResponse
    from src.models import EvaluationMetrics

    async def fake(settings, state):
        assert "Brasília" in state and "ground_truth" in state
        return DecisionResponse(
            probability=probability,
            model="typesafe/jev-1.13",
            metrics=EvaluationMetrics(latency_ms=200),
        )

    monkeypatch.setattr("src.eval.decision.request_decision", fake)
    case = find_case("case_001")
    result = await evaluate_with_decision_model(configured(), case, "Brasília")
    assert result.passed is passed
    assert result.score == probability
    assert result.score_type == "probability"
    assert result.rationale_available is False
    assert "sem racional textual" in result.reason
    assert not result.evidence.get("judge_evidence")


async def test_jev_missing_reported_cost_uses_identified_estimate():
    async def handle(request):
        return httpx.Response(
            200,
            json={
                "model": "typesafe/jev-1.13-20260917",
                "answers": {"passed": {"type": "noul", "noul": 0.97}},
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await request_decision(configured(), "context", client=client)
    assert result.metrics.cost_usd == pytest.approx(0.0000042)
    assert result.metrics.cost_status == "estimated"
    assert result.metrics.cost_source == "pricing_catalog"
    assert result.metrics.cost_formula and result.metrics.pricing_version
