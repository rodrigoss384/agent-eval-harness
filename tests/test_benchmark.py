import pytest

from src.config import Settings
from src.eval.benchmark import BenchmarkManager, BenchmarkRequest, load_samples
from src.eval.benchmark_stats import summarize_benchmark
from src.models import EvaluationMetrics, EvaluationResult
from src.storage import SQLiteStore


def test_curated_samples_are_balanced_and_labels_not_in_state():
    from src.eval.context import evaluation_state

    samples = load_samples()
    assert len(samples) == 48
    assert len({s.case.id for s in samples}) == 24
    assert sum(s.expected_passed for s in samples) == 24
    for s in samples:
        state = evaluation_state(s.case, s.output)
        assert "expected_passed" not in state
        assert s.label_reason not in state


async def test_benchmark_persists_budget_and_comparison(tmp_path, monkeypatch):
    from src.eval.benchmark_models import Benchmark

    store = SQLiteStore(tmp_path / "test.db")
    await store.initialize()
    settings = Settings(
        _env_file=None,
        openai_api_key="fake",
        openrouter_api_key="fake",
        eval_judge_provider="openai",
        eval_judge_model="gpt-4.1-mini",
    )
    manager = BenchmarkManager(settings, store)
    await manager.initialize()
    calls = []

    async def fake(settings, case, output, method, *args):
        persisted = await manager.list()
        assert persisted[0].calls[-1].status == "reserved"
        calls.append(method)
        return EvaluationResult(
            method=method,
            status="passed",
            passed=True,
            score=0.97,
            reason="Resultado de teste",
            correctness_definition=case.correctness_definition,
            metrics=EvaluationMetrics(
                input_tokens=20,
                output_tokens=0,
                total_tokens=20,
                latency_ms=200,
                cost_usd=0.000001,
                cost_status="reported",
                cost_source="provider_response",
            ),
        )

    monkeypatch.setattr("src.eval.benchmark.evaluate_model", fake)
    run = await manager.start(BenchmarkRequest(case_ids=["case_001"], confirm_paid=True))
    await manager.wait(run.benchmark_id)
    result = await manager.get(run.benchmark_id)
    assert isinstance(result, Benchmark)
    assert len(calls) == 12
    assert result.status == "completed"
    assert len(result.runs) == 6
    assert result.accounted_usd == pytest.approx(0.000012)
    summary = summarize_benchmark(result)
    assert summary["distinct_candidates"] == 2
    assert summary["comparison"]["paired_trials"] == 6
    assert summary["methods"]["llm_as_judge"]["accuracy"] == 0.5
    assert summary["methods"]["llm_as_judge"]["confusion"]["fp"] == 1
    await manager.shutdown()
    await store.close()


async def test_budget_stops_before_call_and_preserves_unknown_charge(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "test.db")
    await store.initialize()
    settings = Settings(
        _env_file=None,
        openai_api_key="fake",
        openrouter_api_key="fake",
        eval_judge_provider="openai",
        eval_judge_model="gpt-4.1-mini",
    )
    manager = BenchmarkManager(settings, store)
    await manager.initialize()

    async def fake(*args):
        raise AssertionError("Budget must prevent any provider call")

    monkeypatch.setattr("src.eval.benchmark.evaluate_model", fake)
    run = await manager.start(
        BenchmarkRequest(case_ids=["case_001"], confirm_paid=True, max_cost_usd=0.00000001)
    )
    await manager.wait(run.benchmark_id)
    result = await manager.get(run.benchmark_id)
    assert result.status == "budget_exhausted"
    assert not result.calls
    await store.close()


async def test_immediate_cancel_and_restart_preserve_reservation(tmp_path):
    from src.eval.benchmark_models import Benchmark, BenchmarkCall
    from src.models import EvaluationMethod

    store = SQLiteStore(tmp_path / "restart.db")
    await store.initialize()
    settings = Settings(
        _env_file=None,
        openai_api_key="fake",
        openrouter_api_key="fake",
        eval_judge_provider="openai",
        eval_judge_model="gpt-4.1-mini",
    )
    manager = BenchmarkManager(settings, store)
    await manager.initialize()
    accepted = await manager.start(BenchmarkRequest(case_ids=["case_001"], confirm_paid=True))
    cancelled = await manager.cancel(accepted.benchmark_id)
    assert cancelled.status == "cancelled"
    assert not cancelled.calls
    pending = Benchmark(
        benchmark_id="pending",
        request=BenchmarkRequest(confirm_paid=True),
        dataset_checksum="test",
        samples=load_samples()[:2],
        calls_planned=12,
        status="running",
        accounted_usd=0.01,
        calls=[
            BenchmarkCall(
                sample_id="test",
                trial_index=1,
                method=EvaluationMethod.DECISION_MODEL,
                reserved_usd=0.01,
                accounted_usd=0.01,
            )
        ],
    )
    await manager._save(pending)
    await manager.initialize()
    await manager.initialize()
    interrupted = await manager.get("pending")
    assert interrupted.status == "interrupted"
    assert interrupted.calls[0].status == "interrupted"
    assert interrupted.accounted_usd == 0.01
    assert interrupted.calls[0].accounting == "reservation"
    await store.close()


def test_quality_weights_candidates_not_repetitions_and_sensitivity_is_read_only():
    from src.eval.benchmark_models import Benchmark, BenchmarkTrial
    from src.models import EvaluationMethod

    samples = [s for s in load_samples() if s.case.id == "case_001"]
    benchmark = Benchmark(
        benchmark_id="stats",
        request=BenchmarkRequest(confirm_paid=True),
        samples=samples,
        dataset_checksum="test",
        calls_planned=12,
    )
    # One correct candidate has 3 successes, the incorrect candidate one false positive.
    for sample in samples:
        for trial in range(1, 4 if sample.expected_passed else 2):
            benchmark.runs.append(
                BenchmarkTrial(
                    sample_id=sample.id,
                    trial_index=trial,
                    evaluations=[
                        EvaluationResult(
                            method=EvaluationMethod.DECISION_MODEL,
                            status="passed",
                            passed=True,
                            score=0.9,
                            threshold=1,
                            correctness_definition="test",
                            reason="test",
                        )
                    ],
                )
            )
    before = benchmark.model_dump_json()
    summary = summarize_benchmark(benchmark)
    jev = summary["methods"]["decision_model"]
    assert jev["accuracy"] == 0.5
    assert jev["confusion"] == {"tp": 1, "tn": 0, "fp": 1, "fn": 0}
    assert jev["complete_candidates"] == 1
    assert jev["brier_score"] == pytest.approx(0.41)
    assert sum(b["count"] for b in jev["reliability"]) == 2
    assert summary["comparison"]["unpaired_trials"] == 4
    exploratory = summarize_benchmark(benchmark, 1)
    assert exploratory["methods"]["decision_model"]["confusion"]["fn"] == 1
    assert before == benchmark.model_dump_json()


async def test_call_cap_counts_errors_and_keeps_unknown_cost(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "cap.db")
    await store.initialize()
    manager = BenchmarkManager(
        Settings(
            _env_file=None,
            openai_api_key="fake",
            openrouter_api_key="fake",
            eval_judge_provider="openai",
            eval_judge_model="gpt-4.1-mini",
        ),
        store,
    )
    await manager.initialize()

    async def failed(settings, case, output, method, *args):
        return EvaluationResult(
            method=method,
            status="error",
            reason="timeout",
            correctness_definition=case.correctness_definition,
        )

    monkeypatch.setattr("src.eval.benchmark.evaluate_model", failed)
    accepted = await manager.start(
        BenchmarkRequest(case_ids=["case_001"], confirm_paid=True, max_calls=2)
    )
    await manager.wait(accepted.benchmark_id)
    result = await manager.get(accepted.benchmark_id)
    assert result.status == "budget_exhausted"
    assert len(result.calls) == 2
    assert all(c.accounting == "reservation" for c in result.calls)
    assert result.accounted_usd == sum(c.reserved_usd for c in result.calls)
    assert len(result.runs[0].evaluations) == 2
    await store.close()


async def test_api_benchmark_lifecycle_and_schema(tmp_path, monkeypatch):
    import httpx

    from src.main import create_app

    app = create_app(
        Settings(
            _env_file=None,
            database_path=tmp_path / "api.db",
            openai_api_key="fake",
            openrouter_api_key="fake",
            eval_judge_provider="openai",
            eval_judge_model="gpt-4.1-mini",
        )
    )

    async def fake(settings, case, output, method, *args):
        return EvaluationResult(
            method=method,
            status="failed",
            passed=False,
            score=0.1,
            reason="test",
            correctness_definition=case.correctness_definition,
            metrics=EvaluationMetrics(
                cost_usd=0.000001, cost_status="reported", cost_source="provider_response"
            ),
        )

    monkeypatch.setattr("src.eval.benchmark.evaluate_model", fake)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api:
            preflight = await api.get("/api/eval/benchmarks/preflight")
            assert preflight.json()["ready"]
            assert "fake" not in preflight.text
            schema = (await api.get("/openapi.json")).json()
            assert "decision_model" in schema["components"]["schemas"]["EvaluationMethod"]["enum"]
            created = await api.post(
                "/api/eval/benchmarks", json={"confirm_paid": True, "case_ids": ["case_001"]}
            )
            assert created.status_code == 202
            benchmark_id = created.json()["benchmark_id"]
            await app.state.benchmark_manager.wait(benchmark_id)
            detail = await api.get(f"/api/eval/benchmarks/{benchmark_id}")
            assert detail.json()["status"] == "completed"
            assert len(detail.json()["calls"]) == 12
            events = await api.get(f"/api/eval/benchmarks/{benchmark_id}/events")
            assert "event: progress" in events.text and "event: snapshot" in events.text
            summary = await api.get(f"/api/eval/benchmarks/{benchmark_id}/summary?threshold=0.05")
            assert summary.json()["exploratory_threshold"] == 0.05
            assert (await api.get(f"/api/eval/benchmarks/{benchmark_id}")).json() == detail.json()
            assert len((await api.get("/api/eval/benchmarks")).json()) == 1
            assert (
                await api.post(
                    "/api/eval/benchmarks", json={"confirm_paid": True, "max_cost_usd": 2.01}
                )
            ).status_code == 422
