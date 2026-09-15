import json
from pathlib import Path

from src.dataset import find_case
from src.eval.aggregation import aggregate_trials
from src.eval.pricing import estimate_cost
from src.eval.retrieval import retrieve_chunks
from src.models import FinalVerdict
from src.storage import SQLiteStore


def test_advanced_retrieval_case_has_auditable_ground_truth() -> None:
    case = find_case("case_retrieval_advanced_001")

    assert case is not None
    assert case.difficulty == "advanced"
    assert len(case.reference_context) >= 4
    assert len(case.deterministic_assertions) >= 3
    assert case.retrieval is not None
    assert len(case.retrieval.expected_context_ids) >= 2


def test_bm25_retrieval_returns_expected_incident_chunks() -> None:
    case = find_case("case_retrieval_advanced_001")
    assert case is not None and case.retrieval is not None

    ranked = retrieve_chunks(case.input, case.reference_context, case.retrieval.top_k)

    assert {item.chunk.id for item in ranked[:2]} == set(case.retrieval.expected_context_ids)
    assert ranked[0].score > 0


def test_cost_estimate_exposes_formula_and_catalog_version() -> None:
    estimate = estimate_cost(
        model="gpt-4.1-mini",
        pricing_profile="standard",
        input_tokens=1_000,
        output_tokens=500,
    )

    assert estimate.status == "estimated"
    assert estimate.usd == 0.0012
    assert estimate.catalog_version == "2026-09-09"
    assert "1000" in estimate.formula
    assert estimate.source_url.startswith("https://")


def test_three_trials_are_not_hidden_by_an_average() -> None:
    assert aggregate_trials([FinalVerdict.PASS] * 3) == "stable_pass"
    assert aggregate_trials([FinalVerdict.FAIL] * 3) == "stable_fail"
    assert aggregate_trials([FinalVerdict.PASS, FinalVerdict.FAIL, FinalVerdict.PASS]) == "unstable"
    assert aggregate_trials([FinalVerdict.PASS, FinalVerdict.INCONCLUSIVE]) == "inconclusive"


async def test_storage_migration_v2_persists_session_and_ordered_events(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "live.db")
    await store.initialize()
    document = json.dumps({"session_id": "session_001", "status": "queued"})
    await store.save_session("session_001", "queued", document)
    first = await store.append_session_event("session_001", "session_started", "{}")
    second = await store.append_session_event("session_001", "case_started", "{}")

    assert second > first
    assert await store.get_session("session_001") == document
    assert [event["event_type"] for event in await store.list_session_events("session_001", 0)] == [
        "session_started",
        "case_started",
    ]
    await store.close()
