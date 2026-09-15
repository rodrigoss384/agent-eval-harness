"""Critérios offline do build amplo: dataset, importação, tools, summary e bias."""

import asyncio
from collections import Counter
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.dataset import find_case, load_dataset
from src.eval.deterministic import evaluate_deterministic
from src.eval.summary import nearest_rank
from src.main import create_app
from src.models import CandidateInput, ToolCall


@pytest.fixture
async def client(tmp_path: Path) -> AsyncClient:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "evals.db",
        static_dir=tmp_path / "missing-static",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api


def test_builtin_v2_has_balanced_professional_suite() -> None:
    cases = load_dataset()
    assert len(cases) == 24
    assert len({case.id for case in cases}) == 24
    for category in ("factual", "retrieval", "tool_use"):
        selected = [case for case in cases if case.category == category]
        assert len(selected) == 8
        assert Counter(case.difficulty for case in selected) == {
            "basic": 2,
            "intermediate": 3,
            "advanced": 3,
        }


def test_tool_exact_checks_name_arguments_and_single_call() -> None:
    case = find_case("case_tool_006")
    assert case is not None and case.tool is not None
    valid = CandidateInput(
        output="",
        tool_calls=[ToolCall(name=case.tool.name, arguments=case.tool.expected_arguments)],
    )
    wrong_argument = CandidateInput(
        output="",
        tool_calls=[ToolCall(name=case.tool.name, arguments={"user": "outra"})],
    )
    assert evaluate_deterministic(case, valid).passed is True
    assert evaluate_deterministic(case, wrong_argument).passed is False


def test_tool_canonical_accepts_declared_alias_only() -> None:
    case = find_case("case_tool_001")
    assert case is not None and case.tool is not None
    canonical = case.model_copy(deep=True)
    canonical.deterministic_rule.kind = "tool_canonical"
    candidate = CandidateInput(
        output="",
        tool_calls=[
            ToolCall(
                name=case.tool.canonical_aliases[0],
                arguments=case.tool.expected_arguments,
            )
        ],
    )
    assert evaluate_deterministic(case, candidate).passed is False
    assert evaluate_deterministic(canonical, candidate).passed is True


def test_nearest_rank_percentiles() -> None:
    values = [100, 200, 300, 400, 500]
    assert nearest_rank(values, 0.50) == 300
    assert nearest_rank(values, 0.95) == 500
    assert nearest_rank([], 0.50) is None


async def test_dataset_catalog_and_valid_import(client: AsyncClient) -> None:
    builtin = await client.get("/api/eval/datasets/builtin-v2")
    assert builtin.status_code == 200
    assert builtin.json()["metadata"]["case_count"] == 24
    imported_case = builtin.json()["cases"][0]
    imported_case["id"] = "imported_case_001"
    response = await client.post(
        "/api/eval/datasets/import",
        json={
            "name": "Minha suíte sintética",
            "content": __import__("json").dumps(imported_case, ensure_ascii=False),
            "data_classification": "synthetic",
        },
    )
    assert response.status_code == 201
    dataset_id = response.json()["metadata"]["dataset_id"]
    catalog = await client.get("/api/eval/datasets")
    assert {item["dataset_id"] for item in catalog.json()} == {"builtin-v2", dataset_id}


async def test_import_reports_duplicate_ids_by_line(client: AsyncClient) -> None:
    case = (await client.get("/api/eval/datasets/builtin-v2")).json()["cases"][0]
    content = "\n".join([__import__("json").dumps(case), __import__("json").dumps(case)])
    response = await client.post(
        "/api/eval/datasets/import",
        json={"name": "Duplicado", "content": content, "data_classification": "synthetic"},
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["line"] == 2


async def test_correctness_definition_bias_runs_without_provider(client: AsyncClient) -> None:
    response = await client.post(
        "/api/eval/bias/correctness-definition",
        json={"dataset_id": "builtin-v2", "case_id": "case_tool_001"},
    )
    assert response.status_code == 202
    audit_id = response.json()["audit_id"]
    for _ in range(20):
        audit = await client.get(f"/api/eval/bias/{audit_id}")
        if audit.json()["status"] == "completed":
            break
        await asyncio.sleep(0.01)
    body = audit.json()
    assert body["result"] == "detected"
    assert body["calls_planned"] == 0
    assert body["measurements"]["tool_exact"]["passed"] is False
    assert body["measurements"]["tool_canonical"]["passed"] is True
