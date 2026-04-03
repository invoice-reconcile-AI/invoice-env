"""Deterministic grading helpers for Invoice Reconciliation tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

try:
    from ..models import (Decision, InvoiceReconciliationAction,
                          InvoiceReconciliationReward)
except ImportError:
    from models import (Decision, InvoiceReconciliationAction,
                        InvoiceReconciliationReward)


@dataclass(frozen=True)
class POSelectionGrade:
    reward: float
    po_component: float
    invalid_penalty: float
    current_score: float
    error_message: str | None


@dataclass(frozen=True)
class FinalDecisionGrade:
    reward: float
    final_score: float
    breakdown: InvoiceReconciliationReward


def grade_po_selection(
    action: InvoiceReconciliationAction,
    expected_po_id: str,
    candidate_ids: Iterable[str],
) -> POSelectionGrade:
    candidate_id_set = set(candidate_ids)

    if action.po_id not in candidate_id_set:
        return POSelectionGrade(
            reward=-0.1,
            po_component=0.0,
            invalid_penalty=0.1,
            current_score=0.0,
            error_message=f"Unknown po_id '{action.po_id}'",
        )

    po_component = 0.3 if action.po_id == expected_po_id else 0.0
    current_score = max(0.0, min(1.0, po_component))
    return POSelectionGrade(
        reward=po_component,
        po_component=po_component,
        invalid_penalty=0.0,
        current_score=current_score,
        error_message=None,
    )


def grade_final_decision(
    action: InvoiceReconciliationAction,
    expected_decision: Decision,
    note_keywords: Sequence[str],
    min_keyword_matches: int,
    po_component: float,
    invalid_penalty: float,
    previous_score: float,
) -> FinalDecisionGrade:
    decision_component = 0.4 if action.decision == expected_decision else 0.0

    note_component = 0.0
    note_text = (action.note or "").lower()
    keyword_hits = sum(1 for keyword in note_keywords if keyword in note_text)

    if min_keyword_matches > 0:
        note_fraction = min(1.0, keyword_hits / float(min_keyword_matches))
        note_component = round(0.3 * note_fraction, 4)

    breakdown = InvoiceReconciliationReward(
        po_match_score=po_component,
        decision_score=decision_component,
        note_score=note_component,
        invalid_po_penalty=invalid_penalty,
        final_score=0.0,
    )

    final_score = max(
        0.0,
        min(
            1.0,
            breakdown.po_match_score
            + breakdown.decision_score
            + breakdown.note_score
            - breakdown.invalid_po_penalty,
        ),
    )
    breakdown.final_score = final_score
    incremental_reward = round(final_score - previous_score, 4)

    return FinalDecisionGrade(
        reward=incremental_reward,
        final_score=final_score,
        breakdown=breakdown,
    )
