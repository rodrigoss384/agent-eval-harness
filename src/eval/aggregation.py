"""Agregação explícita das três tentativas de um caso."""

from typing import Literal

from src.models import FinalVerdict

CaseStatus = Literal["stable_pass", "stable_fail", "unstable", "inconclusive"]


def aggregate_trials(verdicts: list[FinalVerdict]) -> CaseStatus:
    """Preserva divergência entre tentativas em vez de escondê-la numa média."""
    if len(verdicts) != 3 or FinalVerdict.INCONCLUSIVE in verdicts:
        return "inconclusive"
    if all(verdict is FinalVerdict.PASS for verdict in verdicts):
        return "stable_pass"
    if all(verdict is FinalVerdict.FAIL for verdict in verdicts):
        return "stable_fail"
    return "unstable"
