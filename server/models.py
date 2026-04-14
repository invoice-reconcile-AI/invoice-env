"""Pydantic models for the Invoice Reconciliation OpenEnv environment.

Multi-step design
-----------------
The reconciliation process is broken into 4 ordered stages:

  Stage 1 – select_po       : Agent inspects the invoice & available PO candidates
                              and picks the best matching PO.
  Stage 2 – compare_items   : Agent compares each invoice line item against the
                              selected PO and GRN, one at a time.
  Stage 3 – flag_discrepancies: Agent explicitly flags each detected discrepancy.
  Stage 4 – final_decision  : Agent issues the definitive approve / flag / reject.

Each env.step() call advances one of these stages and returns an incremental reward.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Document models
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    """A single line item on an invoice or purchase order."""

    description: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    total: Decimal = Field(gt=0)


class Invoice(BaseModel):
    """Represents a vendor invoice submitted for payment."""

    invoice_id: str
    vendor_name: str
    invoice_date: date
    line_items: list[LineItem]
    subtotal: Decimal
    tax: Decimal = Decimal("0.00")
    total_amount: Decimal
    currency: str = "USD"
    po_reference: str | None = None
    notes: str | None = None


class PurchaseOrder(BaseModel):
    """Represents an approved Purchase Order issued by the buyer."""

    po_id: str
    vendor_name: str
    issue_date: date
    line_items: list[LineItem]
    total_amount: Decimal
    currency: str = "USD"
    approved_by: str | None = None


class GoodsReceivedNote(BaseModel):
    """Records what was actually received against a PO."""

    grn_id: str
    po_id: str
    received_date: date
    items_received: list[LineItem]
    received_by: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Discrepancy models (used in observation)
# ---------------------------------------------------------------------------


class DiscrepancyType(str, Enum):
    """Types of discrepancies that can be detected during reconciliation."""

    PRICE_MISMATCH = "price_mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    VENDOR_NAME_MISMATCH = "vendor_name_mismatch"
    PO_NOT_FOUND = "po_not_found"
    DUPLICATE_INVOICE = "duplicate_invoice"
    PARTIAL_DELIVERY = "partial_delivery"
    EXTRA_CHARGE = "extra_charge"
    MISSING_LINE_ITEM = "missing_line_item"
    TAX_MISMATCH = "tax_mismatch"


class Discrepancy(BaseModel):
    """Describes a single discrepancy found during reconciliation."""

    discrepancy_type: DiscrepancyType
    field: str
    invoice_value: Any
    expected_value: Any
    description: str


# ---------------------------------------------------------------------------
# Stage-specific Action models  (discriminated by action_type literal)
# ---------------------------------------------------------------------------


class SelectPOAction(BaseModel):
    """Stage 1: Agent selects the best-matching Purchase Order."""

    action_type: Literal["select_po"] = "select_po"
    po_id: str = Field(
        description="The po_id of the Purchase Order the agent chooses to reconcile against."
    )
    reasoning: str | None = Field(
        None, description="Brief justification for choosing this PO."
    )


class CompareItemAction(BaseModel):
    """Stage 2: Agent compares one invoice line item to the selected PO / GRN."""

    action_type: Literal["compare_item"] = "compare_item"
    invoice_item_index: int = Field(
        description="0-based index into the invoice 'line_items' list."
    )
    po_item_description: str = Field(
        description="Description of the PO line item being compared (verbatim)."
    )
    price_matches: bool = Field(
        description="True if invoice unit_price == PO unit_price for this item."
    )
    quantity_matches: bool = Field(
        description="True if invoice quantity == GRN quantity_received for this item."
    )
    found_in_po: bool = Field(
        description="True if this invoice item has a corresponding entry in the PO."
    )


class FlagDiscrepancyAction(BaseModel):
    """Stage 3: Agent formally flags one identified discrepancy."""

    action_type: Literal["flag_discrepancy"] = "flag_discrepancy"
    discrepancy_type: DiscrepancyType = Field(
        description="The category of discrepancy being flagged."
    )
    details: str = Field(
        description=(
            "Concise human-readable description, e.g. "
            "'Invoice price $1200, PO price $1100 for Laptop Model X'."
        )
    )


class FinalDecisionAction(BaseModel):
    """Stage 4: Agent issues the definitive reconciliation decision."""

    action_type: Literal["final_decision"] = "final_decision"
    decision: Literal["approve", "flag_discrepancy", "reject"] = Field(
        description="Final disposition of the invoice."
    )
    matched_po_id: str | None = Field(
        None, description="po_id of the Purchase Order that was reconciled."
    )
    reasoning: str | None = Field(
        None, description="Detailed explanation for the final decision."
    )
    discrepancy_flags: list[DiscrepancyType] = Field(
        default_factory=list,
        description="Exhaustive list of discrepancy types that influenced this decision.",
    )


# Discriminated union — the single action type accepted by /step
InvoiceAction = Annotated[
    Union[SelectPOAction, CompareItemAction, FlagDiscrepancyAction, FinalDecisionAction],
    Field(discriminator="action_type"),
]


class InvoiceActionWrapper(BaseModel):
    """Wrapper so FastAPI can accept the discriminated-union action via POST body."""

    action: InvoiceAction


# ---------------------------------------------------------------------------
# Observation model
# ---------------------------------------------------------------------------

ReconciliationStage = Literal[
    "select_po",
    "compare_items",
    "flag_discrepancies",
    "final_decision",
    "finished",
]


class InvoiceObservation(BaseModel):
    """The observation returned to the agent at each step."""

    episode_id: str
    task_id: str
    step: int

    # ── Documents ──────────────────────────────────────────────────────────
    invoice: Invoice
    available_pos: list[PurchaseOrder] = Field(
        default_factory=list,
        description="PO candidates available for matching (shown from step 0).",
    )
    goods_received_note: GoodsReceivedNote | None = None

    # ── Running state (revealed progressively) ─────────────────────────────
    selected_po: PurchaseOrder | None = Field(
        None, description="PO chosen by the agent in Stage 1."
    )
    comparison_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Accumulated item-comparison results from Stage 2.",
    )
    flagged_discrepancies: list[Discrepancy] = Field(
        default_factory=list,
        description="Discrepancies explicitly flagged by the agent in Stage 3.",
    )

    # ── Episode metadata ───────────────────────────────────────────────────
    stage: ReconciliationStage = "select_po"
    is_done: bool = False
    reward: float = 0.0
    cumulative_reward: float = 0.0
    info: dict[str, Any] = Field(default_factory=dict)
    feedback: str = Field(
        default="",
        description="Guidance message for the agent about what to do next.",
    )

    # ── Confidence & compliance (Phase 3 rubric: Environment Design 20%) ──
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Per-field confidence scores 0.0–1.0, e.g. {'po_selection': 0.95, 'item_comparison': 0.8}.",
    )
    needs_review: bool = Field(
        default=False,
        description="True if min(confidence) < 0.8 — flags invoice for human review.",
    )
    compliance_check: str | None = Field(
        None,
        description="Compliance rule applied, e.g. 'SOC2_REQUIRED', 'FX_POLICY_REQUIRES_TREASURY_APPROVAL'.",
    )
    action_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Replay log of actions taken in the episode."
    )
    allowed_action_types: list[str] = Field(
        default_factory=list,
        description="Explicit action mask showing which actions are valid for the current stage."
    )
