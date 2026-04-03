"""Typed models for the Invoice Reconciliation environment."""

from __future__ import annotations

from enum import Enum
from typing import List, Literal

from pydantic import BaseModel, Field

try:
    from openenv.core.env_server import Action, Observation, State
except ImportError:
    from openenv_core.env_server import Action, Observation, State


class Decision(str, Enum):
    """Allowed payment workflow decisions."""

    PAY = "pay"
    HOLD = "hold"
    FLAG = "flag"


class InvoiceReconciliationAction(Action):
    """Unified action schema used across all task difficulties."""

    po_id: str = Field(..., description="Selected purchase-order id")
    decision: Decision = Field(..., description="pay | hold | flag")
    note: str = Field(default="", description="Short rationale for the decision")


class POLine(BaseModel):
    """A line item from a purchase order."""

    sku: str
    description: str
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    line_total: float = Field(ge=0)


class PurchaseOrderCandidate(BaseModel):
    """Candidate PO shown to the agent."""

    po_id: str
    vendor_name: str
    currency: str = "USD"
    lines: List[POLine] = Field(default_factory=list)
    total_amount: float = Field(ge=0)


class GRNEntry(BaseModel):
    """Goods-received log entry."""

    po_id: str
    sku: str
    received_qty: float = Field(ge=0)
    receipt_ref: str


class InvoiceReconciliationObservation(Observation):
    """Observation payload sent to the agent."""

    task_id: str
    difficulty: Literal["easy", "medium", "hard"]
    stage: Literal["po_selection", "final_decision", "completed"]
    invoice_text: str
    candidate_pos: List[PurchaseOrderCandidate] = Field(default_factory=list)
    grn_log: List[GRNEntry] = Field(default_factory=list)
    allowed_decisions: List[str] = Field(
        default_factory=lambda: ["pay", "hold", "flag"]
    )
    hints: List[str] = Field(default_factory=list)
    accumulated_score: float = Field(default=0.0, ge=0.0, le=1.0)


class InvoiceReconciliationState(State):
    """Server-side episode state."""

    task_id: str = ""
    difficulty: str = "easy"
    stage: str = "po_selection"
    max_steps: int = 2
    final_score: float = Field(default=0.0, ge=0.0, le=1.0)
    po_id_selected: str | None = None
    decision_submitted: str | None = None


class InvoiceReconciliationReward(BaseModel):
    """Explicit reward model for deterministic grading components."""

    po_match_score: float = Field(default=0.0, ge=0.0, le=0.3)
    decision_score: float = Field(default=0.0, ge=0.0, le=0.4)
    note_score: float = Field(default=0.0, ge=0.0, le=0.3)
    invalid_po_penalty: float = Field(default=0.0, ge=0.0, le=0.1)
    final_score: float = Field(default=0.0, ge=0.0, le=1.0)
