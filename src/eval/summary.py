"""Agregações de sessão sem esconder instabilidade ou custo ausente."""

import math

from src.models import EvaluationMethod, EvaluationSession, SessionSummary


def nearest_rank(values: list[int], percentile: float) -> int | None:
    """Calcula percentil pelo método nearest-rank."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def summarize_session(session: EvaluationSession) -> SessionSummary:
    statuses = list(session.case_statuses.values())
    latencies = [
        run.metrics.total_latency_ms
        for run in session.runs
        if run.metrics.total_latency_ms is not None
    ]
    scores = [
        evaluation.score
        for run in session.runs
        for evaluation in run.evaluations
        if evaluation.method is EvaluationMethod.LLM_AS_JUDGE and evaluation.score is not None
    ]
    known_costs = [run.metrics.cost_usd for run in session.runs if run.metrics.cost_usd is not None]
    stable_passes = statuses.count("stable_pass")
    return SessionSummary(
        session_id=session.session_id,
        total_cases=len(session.request.case_ids),
        total_runs=len(session.runs),
        stable_passes=stable_passes,
        stable_fails=statuses.count("stable_fail"),
        unstable=statuses.count("unstable"),
        inconclusive=statuses.count("inconclusive"),
        stable_pass_rate=(stable_passes / len(statuses)) if statuses else 0,
        latency_p50_ms=nearest_rank(latencies, 0.50),
        latency_p95_ms=nearest_rank(latencies, 0.95),
        total_tokens=sum(run.metrics.total_tokens or 0 for run in session.runs),
        known_cost_usd=sum(known_costs),
        runs_without_cost=len(session.runs) - len(known_costs),
        judge_scores=scores,
    )
