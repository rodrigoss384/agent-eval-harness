"""Match determinístico auditável."""

import re

from src.models import CandidateInput, DatasetCase, EvaluationMethod, EvaluationResult


def evaluate_deterministic(case: DatasetCase, candidate: CandidateInput) -> EvaluationResult:
    """Aplica a regra declarada pelo dataset sem usar LLM."""
    rule = case.deterministic_rule
    actual = candidate.output

    assertion_results = []
    forbidden_hits = []
    if case.deterministic_assertions:
        for assertion in case.deterministic_assertions:
            matched = re.search(assertion.pattern, candidate.output) is not None
            assertion_results.append(
                {
                    "id": assertion.id,
                    "description": assertion.description,
                    "matched": matched,
                    "critical": assertion.critical,
                    "weight": assertion.weight,
                }
            )
        forbidden_hits = [
            pattern for pattern in case.forbidden_patterns if re.search(pattern, candidate.output)
        ]
        critical_passed = all(
            re.search(assertion.pattern, candidate.output) is not None
            for assertion in case.deterministic_assertions
            if assertion.critical
        )
        total_weight = sum(assertion.weight for assertion in case.deterministic_assertions)
        matched_weight = sum(
            assertion.weight
            for assertion in case.deterministic_assertions
            if re.search(assertion.pattern, candidate.output) is not None
        )
        assertion_score = matched_weight / total_weight if total_weight else 0
        passed = critical_passed and assertion_score >= case.threshold and not forbidden_hits
    elif rule.kind == "exact":
        passed = actual == rule.expected
    elif rule.kind == "regex":
        passed = re.fullmatch(rule.expected, actual) is not None
    elif rule.kind in {"tool_exact", "tool_canonical"}:
        call = candidate.tool_calls[0] if candidate.tool_calls else None
        allowed_names = {rule.expected}
        if rule.kind == "tool_canonical" and case.tool:
            allowed_names.update(case.tool.canonical_aliases)
        name_matches = call is not None and call.name in allowed_names
        arguments_match = call is not None and (
            case.tool is None or call.arguments == case.tool.expected_arguments
        )
        passed = name_matches and arguments_match and len(candidate.tool_calls) == 1
        actual = call.name if call else ""
    else:  # pragma: no cover - o schema impede esta condição
        passed = False

    reason = (
        "O valor observado satisfaz a regra determinística declarada."
        if passed
        else "O valor observado diverge da regra determinística declarada."
    )
    return EvaluationResult(
        method=EvaluationMethod.DETERMINISTIC_MATCH,
        status="passed" if passed else "failed",
        correctness_definition=case.correctness_definition,
        passed=passed,
        reason=reason,
        expected=rule.expected,
        actual=actual,
        evidence={
            "rule_kind": rule.kind,
            "assertions": assertion_results,
            "forbidden_hits": forbidden_hits,
            "tool_arguments_expected": case.tool.expected_arguments if case.tool else None,
            "tool_arguments_actual": (
                candidate.tool_calls[0].arguments if candidate.tool_calls else None
            ),
            "tool_aliases": case.tool.canonical_aliases if case.tool else [],
        },
    )
