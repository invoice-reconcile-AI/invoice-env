"""Pydantic models for the Invoice Reconciliation OpenEnv environment."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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
    purchase_order: PurchaseOrder | None = None
    goods_received_note: GoodsReceivedNote | None = None
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
