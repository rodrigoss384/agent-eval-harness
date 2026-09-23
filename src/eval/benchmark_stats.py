"""Estatísticas descritivas com peso igual por candidato e cobertura explícita."""

import math
from collections import defaultdict
from statistics import mean, pstdev
from typing import Any

from src.eval.benchmark_models import Benchmark
from src.models import EvaluationResult


def percentile(values: list[int], p: float) -> int | None:
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def method_metrics(evaluations: list[EvaluationResult]) -> dict[str, Any]:
    grouped: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in evaluations:
        grouped[result.method].append(result)
    output = {}
    for method, results in grouped.items():
        measured = [r.metrics for r in results if r.metrics is not None]
        latencies = [m.latency_ms for m in measured if m.latency_ms is not None]
        costs = [m.cost_usd for m in measured if m.cost_usd is not None]
        output[method] = {
            "calls": len(results),
            "valid": sum(r.passed is not None for r in results),
            "timeouts": sum("Timeout" in str(r.evidence.get("error_type", "")) for r in results),
            "errors": sum(r.status in {"error", "unavailable"} for r in results),
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
            "latency_samples": len(latencies),
            "known_cost_usd": sum(costs),
            "calls_without_cost": len(results) - len(costs),
            "reported_cost_usd": sum(
                m.cost_usd or 0 for m in measured if m.cost_status == "reported"
            ),
            "estimated_cost_usd": sum(
                m.cost_usd or 0 for m in measured if m.cost_status == "estimated"
            ),
            "input_tokens": sum(m.input_tokens or 0 for m in measured),
            "output_tokens": sum(m.output_tokens or 0 for m in measured),
            "calls_without_tokens": len(results)
            - sum(m.total_tokens is not None for m in measured),
            "models": sorted({r.judge_model for r in results if r.judge_model}),
            "providers": sorted({r.judge_provider for r in results if r.judge_provider}),
        }
    return output


def paired_metrics(groups: list[list[EvaluationResult]]) -> dict[str, Any]:
    agreements = disagreements = 0
    for results in groups:
        pair = {str(r.method): r for r in results if r.passed is not None}
        if "llm_as_judge" in pair and "decision_model" in pair:
            if pair["llm_as_judge"].passed == pair["decision_model"].passed:
                agreements += 1
            else:
                disagreements += 1
    total = agreements + disagreements
    return {
        "paired_trials": total,
        "agreements": agreements,
        "disagreements": disagreements,
        "agreement_rate": agreements / total if total else None,
        "unpaired_trials": len(groups) - total,
    }


def summarize_benchmark(benchmark: Benchmark, threshold: float | None = None) -> dict[str, Any]:
    samples = {s.id: s for s in benchmark.samples}
    groups = [r.evaluations for r in benchmark.runs]
    metrics = method_metrics([e for g in groups for e in g])
    by_method: dict[str, dict[str, list[EvaluationResult]]] = defaultdict(lambda: defaultdict(list))
    for run in benchmark.runs:
        for result in run.evaluations:
            if result.passed is not None and result.score is not None:
                by_method[result.method][run.sample_id].append(result)
    for method in ("llm_as_judge", "decision_model"):
        values = by_method[method]
        item = metrics.setdefault(method, method_metrics([]).get(method, {}))
        confusion = {"tp": 0.0, "tn": 0.0, "fp": 0.0, "fn": 0.0}
        unstable = 0
        spreads: list[float] = []
        briers: list[float] = []
        reliability: list[list[tuple[float, bool]]] = [[] for _ in range(5)]
        for sample_id, results in values.items():
            expected = samples[sample_id].expected_passed
            scores = [float(r.score) for r in results if r.score is not None]
            passed = [
                r.passed if threshold is None else float(r.score or 0) >= threshold for r in results
            ]
            unstable += len(set(passed)) > 1
            if len(scores) >= 2:
                spreads.append(pstdev(scores))
            for p in passed:
                key = "tp" if p and expected else "fp" if p else "fn" if expected else "tn"
                confusion[key] += 1 / len(results)
            if method == "decision_model":
                briers.append(mean((score - int(expected)) ** 2 for score in scores))
                # One point per distinct candidate, not three independent samples.
                score = mean(scores)
                reliability[min(4, int(score * 5))].append((score, expected))
        tp, tn, fp, fn = (confusion[k] for k in ("tp", "tn", "fp", "fn"))
        n = len(values)
        item.update(
            {
                "distinct_candidates": n,
                "expected_candidates": len(samples),
                "complete_candidates": sum(len(v) == 3 for v in values.values()),
                "accuracy": (tp + tn) / n if n else None,
                "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                "confusion": confusion,
                "unstable_candidates": unstable,
                "mean_score_stddev": mean(spreads) if spreads else None,
                "brier_score": mean(briers) if briers else None,
                "reliability": [
                    {
                        "lower": i / 5,
                        "upper": (i + 1) / 5,
                        "count": len(bucket),
                        "mean_probability": mean(p for p, _ in bucket) if bucket else None,
                        "observed_frequency": mean(int(y) for _, y in bucket) if bucket else None,
                    }
                    for i, bucket in enumerate(reliability)
                ]
                if method == "decision_model"
                else [],
            }
        )
    return {
        "benchmark_id": benchmark.benchmark_id,
        "status": benchmark.status,
        "distinct_cases": len({s.case.id for s in benchmark.samples}),
        "distinct_candidates": len(samples),
        "trials": len(benchmark.runs),
        "methods": metrics,
        "comparison": paired_metrics(groups),
        "exploratory_threshold": threshold,
        "accounted_usd": benchmark.accounted_usd,
        "calls_attempted": len(benchmark.calls),
        "uncertain_calls": sum(c.accounting == "reservation" for c in benchmark.calls),
        "weighting": (
            "Cada candidato pesa 1; suas repetições dividem "
            "esse peso. Erros são excluídos da qualidade e mostrados na cobertura."
        ),
        "limitations": [
            "Amostra sintética pequena: repetições não são casos independentes.",
            "Latências incluem rede e serviços diferentes: OpenAI e OpenRouter.",
            "Nota do LLM não é probabilidade calibrada; Brier se aplica somente ao Jev.",
            (
                "Curva de confiabilidade usa a probabilidade média por "
                "candidato; Brier usa a média do erro quadrático das repetições."
            ),
            "O protocolo não demonstra ausência de viés, generalização ou superioridade universal.",
            (
                "Custos informados e estimados são distintos; valores ausentes "
                "não significam gratuidade."
            ),
            (
                "Limiar exploratório não altera o veredito registrado nem o "
                "booleano originalmente retornado pelo LLM."
            ),
        ],
    }
