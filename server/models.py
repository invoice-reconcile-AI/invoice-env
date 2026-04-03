"""Pydantic models for the Invoice Reconciliation OpenEnv environment."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    """A single line item on an invoice or purchase order."""

    description: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    total: Decimal = Field(gt=0)


class Invoice(BaseModel):
    """Represents a vendor invoice submitted for payment."""

    # ── Core identifiers ────────────────────────────────────────────────────
    invoice_id: str = Field(..., description="Unique identifier for the invoice (e.g., 'INV-2026-001').")
    vendor_name: str = Field(..., description="Name of the vendor as it appears on the invoice.")
    invoice_date: str = Field(..., description="Date of the invoice (YYYY-MM-DD).")
    due_date: str = Field(..., description="Date by which the invoice is due (YYYY-MM-DD).")

    # ── Amounts ─────────────────────────────────────────────────────────────
    subtotal: Decimal = Field(..., description="Pre-tax subtotal of all line items.")
    tax: Decimal = Field(Decimal("0.00"), description="Tax amount applied to the invoice.")
    total_amount: float = Field(..., description="Total monetary amount requested on the invoice (subtotal + tax).")
    currency: str = Field("USD", description="Currency of the invoice amount (e.g., 'USD', 'EUR').")

    # ── Structured line items (for precise discrepancy checks) ───────────────
    line_items: List[LineItem] = Field(..., description="Detailed list of billed line items, each with description, quantity, unit price, and total.")
    items_billed: Dict[str, int] = Field(..., description="Summary map of item descriptions to billed quantities for quick agent lookup (e.g., {'Widget A': 10}).")

    # ── PO linkage ───────────────────────────────────────────────────────────
    extracted_po_ref: Optional[str] = Field(
        None,
        description=(
            "The Purchase Order reference explicitly extracted from a structured field on the "
            "invoice, if available. May be None for medium-difficulty tasks where the PO ref "
            "is embedded only in raw_text_content."
        ),
    )

    # ── Raw document text (key for medium-difficulty fuzzy tasks) ────────────
    raw_text_content: str = Field(
        ...,
        description=(
            "Full text content extracted from the invoice document (simulates OCR/PDF parse). "
            "May be messy. The agent should read this to find embedded PO references, "
            "payment notes, or any details not captured in structured fields."
        ),
    )

    # ── Legacy compatibility fields ───────────────────────────────────────────
    notes: Optional[str] = Field(None, description="Free-text notes attached to the invoice.")

    # ── INTERNAL grading field — NOT exposed to the agent ────────────────────
    discrepancy_details: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "INTERNAL: injected by the scenario generator to record what discrepancies were "
            "deliberately introduced into this invoice. The agent does NOT see this field; "
            "it must infer discrepancies from raw_text_content, extracted_po_ref, and the PO/GRN."
        ),
    )


class PurchaseOrder(BaseModel):
    """Represents an approved Purchase Order issued by the buyer."""

    po_id: str = Field(..., description="Unique identifier for the Purchase Order (e.g., 'PO-2026-001').")
    vendor_name: str = Field(..., description="Name of the vendor from whom the items are ordered.")
    issue_date: date = Field(..., description="Date the Purchase Order was issued (YYYY-MM-DD).")
    line_items: List[LineItem] = Field(..., description="Detailed list of line items ordered, each with description, quantity, unit price, and total.")
    total_amount: Decimal = Field(..., description="Total monetary amount of the Purchase Order.")
    currency: str = Field("USD", description="Currency of the Purchase Order amount (e.g., 'USD', 'EUR').")
    items_ordered: Dict[str, int] = Field(..., description="Summary map of item descriptions to ordered quantities for quick agent lookup (e.g., {'Widget A': 10, 'Gadget B': 5}).")
    status: Literal["open", "closed", "partially_received", "cancelled"] = Field("open", description="Current status of the PO.")
    payment_terms: str = Field("Net 30", description="Payment terms for the PO (e.g., 'Net 30', 'Due on Receipt').")
    approved_by: Optional[str] = Field(None, description="Name or ID of the person who approved this Purchase Order.")


class GoodsReceivedNote(BaseModel):
    """Records what was actually received against a PO."""

    grn_id: str
    po_id: str
    received_date: date
    items_received: list[LineItem]
    received_by: str | None = None
    notes: str | None = None


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


class Discrepancy(BaseModel):
    """Describes a single discrepancy found during reconciliation."""

    discrepancy_type: DiscrepancyType
    field: str
    invoice_value: Any
    expected_value: Any
    description: str


class InvoiceObservation(BaseModel):
    """The observation returned to the agent at each step."""

    episode_id: str
    task_id: str
    step: int
    invoice: Invoice
    candidate_pos: List[PurchaseOrder] = Field(default_factory=list, description="A list of potential Purchase Orders the agent could match this invoice against.")
    grn_log: List[GoodsReceivedNote] = Field(default_factory=list, description="A log of all Goods Received Notes. The agent must match these to verify physical quantities received.")
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    is_done: bool = False
    reward: float = 0.0
    info: dict[str, Any] = Field(default_factory=dict)


class ActionType(str, Enum):
    """Possible actions an agent can take during reconciliation."""

    APPROVE = "approve"
    REJECT = "reject"
    FLAG_DISCREPANCY = "flag_discrepancy"
    REQUEST_CREDIT_NOTE = "request_credit_note"
    ESCALATE = "escalate"
    MATCH_TO_PO = "match_to_po"


class InvoiceAction(BaseModel):
    """An action submitted by the agent to advance the episode."""

    action_type: ActionType
    discrepancy_flags: list[DiscrepancyType] = Field(default_factory=list)
    matched_po_id: str | None = None
    reasoning: str | None = None


class InvoiceReward(BaseModel):
    """Granular reward structure for evaluation."""

    score: float = Field(..., ge=0.0, le=1.0, description="Overall score for the task (0.0 to 1.0).")
    correct_decision_made: bool = Field(..., description="Whether the core action (Approve/Hold/Flag) was correct.")
    correct_po_identified: bool = Field(..., description="Whether the correct Purchase Order was linked.")
    discrepancy_correctly_noted: bool = Field(..., description="Whether the discrepancies were correctly identified and explained.")
    reason: str = Field(..., description="Detailed explanation of the score calculation.")
