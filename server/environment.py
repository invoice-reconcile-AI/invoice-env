"""Invoice Reconciliation environment implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
from uuid import uuid4

try:
    from openenv.core.env_server.interfaces import Environment
except ImportError as exc:
    raise ImportError(
        "openenv-core is required. Install dependencies from requirements.txt"
    ) from exc

try:
    from ..models import (
        Decision,
        GRNEntry,
        InvoiceReconciliationAction,
        InvoiceReconciliationObservation,
        InvoiceReconciliationReward,
        InvoiceReconciliationState,
        POLine,
        PurchaseOrderCandidate,
    )
except ImportError:
    from models import (
        Decision,
        GRNEntry,
        InvoiceReconciliationAction,
        InvoiceReconciliationObservation,
        InvoiceReconciliationReward,
        InvoiceReconciliationState,
        POLine,
        PurchaseOrderCandidate,
    )

from .grader import grade_final_decision, grade_po_selection


@dataclass(frozen=True)
class TaskScenario:
    task_id: str
    difficulty: str
    invoice_text: str
    candidate_pos: List[PurchaseOrderCandidate]
    grn_log: List[GRNEntry]
    expected_po_id: str
    expected_decision: Decision
    note_keywords: List[str]
    note_keyword_min_matches: int
    hints: List[str]


def _line(sku: str, description: str, quantity: float, unit_price: float) -> POLine:
    return POLine(
        sku=sku,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        line_total=round(quantity * unit_price, 2),
    )


def _po(
    po_id: str,
    vendor_name: str,
    lines: List[POLine],
    currency: str = "USD",
) -> PurchaseOrderCandidate:
    return PurchaseOrderCandidate(
        po_id=po_id,
        vendor_name=vendor_name,
        currency=currency,
        lines=lines,
        total_amount=round(sum(line.line_total for line in lines), 2),
    )


def _build_scenarios() -> Dict[str, TaskScenario]:
    easy_po = _po(
        "PO-7001",
        "Acme Supplies Ltd",
        [
            _line("LAP-15", "Laptop 15-inch", 5, 1100.0),
            _line("DOCK-USB", "USB-C Dock", 5, 120.0),
        ],
    )
    easy_candidates = [
        easy_po,
        _po(
            "PO-6100",
            "Delta Office Inc",
            [_line("MON-24", "24 inch Monitor", 7, 180.0)],
        ),
        _po(
            "PO-8120",
            "Northwind IT",
            [_line("KB-MECH", "Mechanical Keyboard", 9, 85.0)],
        ),
    ]
    easy_grn = [
        GRNEntry(
            po_id="PO-7001", sku="LAP-15", received_qty=5, receipt_ref="GRN-10011"
        ),
        GRNEntry(
            po_id="PO-7001", sku="DOCK-USB", received_qty=5, receipt_ref="GRN-10011"
        ),
    ]

    medium_po = _po(
        "PO-7002",
        "Acme Supplies Ltd",
        [
            _line("CHAIR-ERG", "Ergonomic Chair", 20, 245.0),
            _line("PAD-XL", "Desk Pad XL", 20, 14.0),
        ],
    )
    medium_candidates = [
        _po(
            "PO-7004",
            "Acme Supplies Ltd",
            [_line("CHAIR-ERG", "Ergonomic Chair", 20, 249.0)],
        ),
        medium_po,
        _po(
            "PO-9020",
            "Blue Ocean Furnishings",
            [_line("DESK-STD", "Standard Desk", 10, 399.0)],
        ),
    ]
    medium_grn = [
        GRNEntry(
            po_id="PO-7002", sku="CHAIR-ERG", received_qty=20, receipt_ref="GRN-10022"
        ),
        GRNEntry(
            po_id="PO-7002", sku="PAD-XL", received_qty=20, receipt_ref="GRN-10022"
        ),
    ]

    hard_po = _po(
        "PO-7003",
        "Global Tech Solutions Inc",
        [
            _line("LAP-17", "Laptop 17-inch", 10, 1400.0),
            _line("MOU-WL", "Wireless Mouse", 10, 35.0),
        ],
    )
    hard_candidates = [
        hard_po,
        _po(
            "PO-7009",
            "Global Tech Solutions Inc",
            [_line("LAP-17", "Laptop 17-inch", 12, 1400.0)],
        ),
        _po("PO-6555", "Orbit Electronics", [_line("SSD-2TB", "2TB SSD", 14, 210.0)]),
    ]
    hard_grn = [
        GRNEntry(
            po_id="PO-7003", sku="LAP-17", received_qty=10, receipt_ref="GRN-10033"
        ),
        GRNEntry(
            po_id="PO-7003", sku="MOU-WL", received_qty=8, receipt_ref="GRN-10033"
        ),
    ]

    return {
        "easy-exact-match": TaskScenario(
            task_id="easy-exact-match",
            difficulty="easy",
            invoice_text=(
                "Invoice INV-5001 from Acme Supplies Ltd for PO-7001. "
                "Items: 5x Laptop 15-inch @ 1100.00, 5x USB-C Dock @ 120.00. "
                "Subtotal 6100.00, Tax 0.00, Total 6100.00."
            ),
            candidate_pos=easy_candidates,
            grn_log=easy_grn,
            expected_po_id="PO-7001",
            expected_decision=Decision.PAY,
            note_keywords=["match", "approved", "no discrepancy"],
            note_keyword_min_matches=1,
            hints=["Exact totals and quantities should reconcile cleanly."],
        ),
        "medium-fuzzy-tolerance": TaskScenario(
            task_id="medium-fuzzy-tolerance",
            difficulty="medium",
            invoice_text=(
                "Invoice INV-5002 from ACME SUPPLIES LTD for PO-7002. "
                "Items: 20x Ergonomic Chair @ 248.68, 20x Desk Pad XL @ 14.00. "
                "Subtotal 5253.60, Tax 0.00, Total 5253.60. "
                "Note: small variance due to rounding policy."
            ),
            candidate_pos=medium_candidates,
            grn_log=medium_grn,
            expected_po_id="PO-7002",
            expected_decision=Decision.PAY,
            note_keywords=["tolerance", "rounding", "within"],
            note_keyword_min_matches=1,
            hints=["This task allows a small amount tolerance (<2%)."],
        ),
        "hard-discrepancy-detection": TaskScenario(
            task_id="hard-discrepancy-detection",
            difficulty="hard",
            invoice_text=(
                "Invoice INV-5003 from Global Tech Solutions Inc for PO-7003. "
                "Items: 10x Laptop 17-inch @ 1500.00, 10x Wireless Mouse @ 35.00, "
                "10x Extended Warranty @ 50.00. "
                "Observed issues: potential price overcharge and unmatched warranty line."
            ),
            candidate_pos=hard_candidates,
            grn_log=hard_grn,
            expected_po_id="PO-7003",
            expected_decision=Decision.FLAG,
            note_keywords=[
                "price mismatch",
                "quantity mismatch",
                "extra charge",
                "warranty",
            ],
            note_keyword_min_matches=2,
            hints=[
                "Look for overcharge, short receipt quantity, and extra line items."
            ],
        ),
    }


class InvoiceReconciliationEnvironment(
    Environment[
        InvoiceReconciliationAction,
        InvoiceReconciliationObservation,
        InvoiceReconciliationState,
    ]
):
    """Accounts-payable reconciliation environment with deterministic grading."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True
    MAX_STEPS: int = 2

    def __init__(self) -> None:
        self._scenarios = _build_scenarios()
        self._scenario: TaskScenario | None = None
        self._state = InvoiceReconciliationState(episode_id=str(uuid4()), step_count=0)
        self._po_component = 0.0
        self._invalid_penalty = 0.0
        self._current_score = 0.0
        self._last_action_error: str | None = None

    def reset(
        self,
        task_id: str = "easy-exact-match",
        seed: int | None = None,
        episode_id: str | None = None,
        **kwargs,
    ) -> InvoiceReconciliationObservation:
        del seed, kwargs

        if task_id not in self._scenarios:
            valid = ", ".join(sorted(self._scenarios.keys()))
            raise ValueError(f"Unknown task_id '{task_id}'. Valid options: {valid}")

        self._scenario = self._scenarios[task_id]
        self._po_component = 0.0
        self._invalid_penalty = 0.0
        self._current_score = 0.0
        self._last_action_error = None

        self._state = InvoiceReconciliationState(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=self._scenario.task_id,
            difficulty=self._scenario.difficulty,
            stage="po_selection",
            max_steps=self.MAX_STEPS,
            final_score=0.0,
            po_id_selected=None,
            decision_submitted=None,
        )

        return self._build_observation(reward=0.0, done=False)

    def step(
        self,
        action: InvoiceReconciliationAction,
        timeout_s: float | None = None,
        **kwargs,
    ) -> InvoiceReconciliationObservation:
        del timeout_s, kwargs

        if self._scenario is None:
            fallback_task = self._scenarios["easy-exact-match"]
            self._scenario = fallback_task
            self._state = InvoiceReconciliationState(
                episode_id=str(uuid4()),
                step_count=0,
                task_id=fallback_task.task_id,
                difficulty=fallback_task.difficulty,
                stage="completed",
                max_steps=self.MAX_STEPS,
                final_score=0.0,
                po_id_selected=None,
                decision_submitted=None,
            )
            self._current_score = 0.0
            self._last_action_error = "No active episode found. Click Reset Environment before taking an action."
            return self._build_observation(reward=0.0, done=True)

        if self._state.stage == "completed":
            self._last_action_error = "Episode already completed. Click Reset Environment to start a new task."
            return self._build_observation(reward=0.0, done=True)

        self._state.step_count += 1

        if self._state.step_count == 1:
            reward = self._grade_po_selection(action)
            self._state.stage = "final_decision"
            self._state.po_id_selected = action.po_id
            return self._build_observation(reward=reward, done=False)

        reward = self._grade_final_decision(action)
        self._state.stage = "completed"
        self._state.decision_submitted = action.decision.value
        self._state.final_score = self._current_score
        return self._build_observation(reward=reward, done=True)

    @property
    def state(self) -> InvoiceReconciliationState:
        return self._state

    def _grade_po_selection(self, action: InvoiceReconciliationAction) -> float:
        assert self._scenario is not None

        grade = grade_po_selection(
            action=action,
            expected_po_id=self._scenario.expected_po_id,
            candidate_ids=[po.po_id for po in self._scenario.candidate_pos],
        )

        self._invalid_penalty = grade.invalid_penalty
        self._last_action_error = grade.error_message
        self._po_component = grade.po_component
        self._current_score = grade.current_score
        return grade.reward

    def _grade_final_decision(self, action: InvoiceReconciliationAction) -> float:
        assert self._scenario is not None

        grade = grade_final_decision(
            action=action,
            expected_decision=self._scenario.expected_decision,
            note_keywords=self._scenario.note_keywords,
            min_keyword_matches=self._scenario.note_keyword_min_matches,
            po_component=self._po_component,
            invalid_penalty=self._invalid_penalty,
            previous_score=self._current_score,
        )

        self._current_score = grade.final_score
        self._last_action_error = None
        return grade.reward

    def _build_observation(
        self,
        reward: float,
        done: bool,
    ) -> InvoiceReconciliationObservation:
        if self._scenario is None:
            raise RuntimeError("No active scenario. Call reset() first.")

        if self._state.stage == "po_selection":
            stage_hints = ["Choose the most likely PO id first."]
        elif self._state.stage == "final_decision":
            stage_hints = ["Now provide final decision and rationale note."]
        else:
            stage_hints = ["Episode complete."]

        metadata = {
            "benchmark": "invoice_reconciliation",
            "task_description": self._scenario.invoice_text,
            "last_action_error": self._last_action_error,
            "final_score": self._current_score,
            "weights": {"po_id": 0.3, "decision": 0.4, "note": 0.3},
        }

        return InvoiceReconciliationObservation(
            done=done,
            reward=reward,
            task_id=self._scenario.task_id,
            difficulty=self._scenario.difficulty,
            stage=self._state.stage,
            invoice_text=self._scenario.invoice_text,
            candidate_pos=[
                po.model_copy(deep=True) for po in self._scenario.candidate_pos
            ],
            grn_log=[entry.model_copy(deep=True) for entry in self._scenario.grn_log],
            allowed_decisions=["pay", "hold", "flag"],
            hints=self._scenario.hints + stage_hints,
            accumulated_score=self._current_score,
            metadata=metadata,
        )
