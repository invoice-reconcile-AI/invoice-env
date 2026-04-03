"""OpenEnv environment logic for Invoice Reconciliation.

Implements the standard OpenEnv API: reset(), step(), and state().
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from server.models import (
    ActionType,
    Discrepancy,
    DiscrepancyType,
    GoodsReceivedNote,
    Invoice,
    InvoiceAction,
    InvoiceObservation,
    LineItem,
    PurchaseOrder,
)

# ---------------------------------------------------------------------------
# Scenario definitions – keyed by task_id
# ---------------------------------------------------------------------------

_SCENARIOS: dict[str, dict[str, Any]] = {
    "easy-exact-match": {
        "description": "Invoice amounts and line items exactly match the PO.",
        "invoice": Invoice(
            invoice_id="INV-1001",
            vendor_name="Acme Supplies Ltd.",
            invoice_date=date(2025, 3, 10),
            line_items=[
                LineItem(
                    description="Office Chair",
                    quantity=Decimal("10"),
                    unit_price=Decimal("150.00"),
                    total=Decimal("1500.00"),
                ),
                LineItem(
                    description="Desk Lamp",
                    quantity=Decimal("20"),
                    unit_price=Decimal("25.00"),
                    total=Decimal("500.00"),
                ),
            ],
            subtotal=Decimal("2000.00"),
            tax=Decimal("200.00"),
            total_amount=Decimal("2200.00"),
            currency="USD",
            po_reference="PO-5001",
        ),
        "purchase_order": PurchaseOrder(
            po_id="PO-5001",
            vendor_name="Acme Supplies Ltd.",
            issue_date=date(2025, 3, 1),
            line_items=[
                LineItem(
                    description="Office Chair",
                    quantity=Decimal("10"),
                    unit_price=Decimal("150.00"),
                    total=Decimal("1500.00"),
                ),
                LineItem(
                    description="Desk Lamp",
                    quantity=Decimal("20"),
                    unit_price=Decimal("25.00"),
                    total=Decimal("500.00"),
                ),
            ],
            total_amount=Decimal("2000.00"),
            currency="USD",
            items_ordered={"Office Chair": 10, "Desk Lamp": 20},
            status="open",
            payment_terms="Net 30",
            approved_by="procurement@buyer.com",
        ),
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-3001",
            po_id="PO-5001",
            received_date=date(2025, 3, 8),
            items_received=[
                LineItem(
                    description="Office Chair",
                    quantity=Decimal("10"),
                    unit_price=Decimal("150.00"),
                    total=Decimal("1500.00"),
                ),
                LineItem(
                    description="Desk Lamp",
                    quantity=Decimal("20"),
                    unit_price=Decimal("25.00"),
                    total=Decimal("500.00"),
                ),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_action": ActionType.APPROVE,
        "expected_discrepancies": [],
    },
    "medium-fuzzy-match": {
        "description": (
            "Vendor name has minor text variation and one unit price differs "
            "by a small rounding amount, requiring fuzzy matching."
        ),
        "invoice": Invoice(
            invoice_id="INV-2002",
            vendor_name="ACME Supplies Ltd",  # capitalisation differs
            invoice_date=date(2025, 3, 15),
            line_items=[
                LineItem(
                    description="Ergonomic Office Chair",  # slight wording change
                    quantity=Decimal("5"),
                    unit_price=Decimal("152.00"),  # $2 over PO price
                    total=Decimal("760.00"),
                ),
                LineItem(
                    description="USB Hub 4-Port",
                    quantity=Decimal("15"),
                    unit_price=Decimal("18.00"),
                    total=Decimal("270.00"),
                ),
            ],
            subtotal=Decimal("1030.00"),
            tax=Decimal("103.00"),
            total_amount=Decimal("1133.00"),
            currency="USD",
            po_reference="PO-5002",
        ),
        "purchase_order": PurchaseOrder(
            po_id="PO-5002",
            vendor_name="Acme Supplies Ltd.",
            issue_date=date(2025, 3, 5),
            line_items=[
                LineItem(
                    description="Office Chair",
                    quantity=Decimal("5"),
                    unit_price=Decimal("150.00"),
                    total=Decimal("750.00"),
                ),
                LineItem(
                    description="USB Hub 4-Port",
                    quantity=Decimal("15"),
                    unit_price=Decimal("18.00"),
                    total=Decimal("270.00"),
                ),
            ],
            total_amount=Decimal("1020.00"),
            currency="USD",
            items_ordered={"Office Chair": 5, "USB Hub 4-Port": 15},
            status="open",
            payment_terms="Net 30",
            approved_by="procurement@buyer.com",
        ),
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-3002",
            po_id="PO-5002",
            received_date=date(2025, 3, 13),
            items_received=[
                LineItem(
                    description="Office Chair",
                    quantity=Decimal("5"),
                    unit_price=Decimal("150.00"),
                    total=Decimal("750.00"),
                ),
                LineItem(
                    description="USB Hub 4-Port",
                    quantity=Decimal("15"),
                    unit_price=Decimal("18.00"),
                    total=Decimal("270.00"),
                ),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_action": ActionType.FLAG_DISCREPANCY,
        "expected_discrepancies": [
            DiscrepancyType.VENDOR_NAME_MISMATCH,
            DiscrepancyType.PRICE_MISMATCH,
        ],
    },
    "hard-discrepancy-detection": {
        "description": (
            "Multiple discrepancies: partial delivery, price mismatch on two items, "
            "and an extra charge not present in the PO."
        ),
        "invoice": Invoice(
            invoice_id="INV-3003",
            vendor_name="Global Tech Solutions Inc.",
            invoice_date=date(2025, 3, 20),
            line_items=[
                LineItem(
                    description="Laptop Model X",
                    quantity=Decimal("10"),
                    unit_price=Decimal("1200.00"),  # PO has $1100
                    total=Decimal("12000.00"),
                ),
                LineItem(
                    description="Wireless Mouse",
                    quantity=Decimal("10"),  # only 8 delivered
                    unit_price=Decimal("35.00"),
                    total=Decimal("350.00"),
                ),
                LineItem(
                    description="Extended Warranty",  # not in PO
                    quantity=Decimal("10"),
                    unit_price=Decimal("50.00"),
                    total=Decimal("500.00"),
                ),
            ],
            subtotal=Decimal("12850.00"),
            tax=Decimal("1285.00"),
            total_amount=Decimal("14135.00"),
            currency="USD",
            po_reference="PO-5003",
        ),
        "purchase_order": PurchaseOrder(
            po_id="PO-5003",
            vendor_name="Global Tech Solutions Inc.",
            issue_date=date(2025, 3, 10),
            line_items=[
                LineItem(
                    description="Laptop Model X",
                    quantity=Decimal("10"),
                    unit_price=Decimal("1100.00"),
                    total=Decimal("11000.00"),
                ),
                LineItem(
                    description="Wireless Mouse",
                    quantity=Decimal("10"),
                    unit_price=Decimal("35.00"),
                    total=Decimal("350.00"),
                ),
            ],
            total_amount=Decimal("11350.00"),
            currency="USD",
            items_ordered={"Laptop Model X": 10, "Wireless Mouse": 10},
            status="open",
            payment_terms="Net 30",
            approved_by="procurement@buyer.com",
        ),
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-3003",
            po_id="PO-5003",
            received_date=date(2025, 3, 18),
            items_received=[
                LineItem(
                    description="Laptop Model X",
                    quantity=Decimal("10"),
                    unit_price=Decimal("1100.00"),
                    total=Decimal("11000.00"),
                ),
                LineItem(
                    description="Wireless Mouse",
                    quantity=Decimal("8"),  # only 8 received
                    unit_price=Decimal("35.00"),
                    total=Decimal("280.00"),
                ),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_action": ActionType.REJECT,
        "expected_discrepancies": [
            DiscrepancyType.PRICE_MISMATCH,
            DiscrepancyType.QUANTITY_MISMATCH,
            DiscrepancyType.EXTRA_CHARGE,
        ],
    },
}

# ---------------------------------------------------------------------------
# Reward constants
# ---------------------------------------------------------------------------

_REWARD_CORRECT = 1.0
_REWARD_PARTIAL = 0.5
_REWARD_WRONG = -1.0


# ---------------------------------------------------------------------------
# Environment class
# ---------------------------------------------------------------------------


class InvoiceReconciliationEnv:
    """Stateful OpenEnv environment for Invoice Reconciliation.

    Each call to ``reset()`` starts a fresh episode for the given task.
    ``step()`` evaluates the agent's action and returns the next observation.
    ``state()`` returns the current observation without advancing the episode.
    """

    def __init__(self) -> None:
        self._observation: InvoiceObservation | None = None
        self._scenario: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public OpenEnv API
    # ------------------------------------------------------------------

    def reset(self, task_id: str) -> InvoiceObservation:
        """Initialise a new episode for *task_id* and return the first observation."""
        if task_id not in _SCENARIOS:
            raise ValueError(
                f"Unknown task_id '{task_id}'. "
                f"Valid tasks: {list(_SCENARIOS.keys())}"
            )

        self._scenario = _SCENARIOS[task_id]
        episode_id = str(uuid.uuid4())

        self._observation = InvoiceObservation(
            episode_id=episode_id,
            task_id=task_id,
            step=0,
            invoice=self._scenario["invoice"],
            purchase_order=self._scenario.get("purchase_order"),
            goods_received_note=self._scenario.get("goods_received_note"),
            discrepancies=[],
            is_done=False,
            reward=0.0,
            info={"description": self._scenario["description"]},
        )
        return self._observation

    def step(self, action: InvoiceAction) -> InvoiceObservation:
        """Process *action* and return the updated observation.

        Rewards:
        - ``+1.0`` for a fully correct action (right type + all discrepancies flagged).
        - ``+0.5`` for a partially correct action (right type, incomplete discrepancy set).
        - ``-1.0`` for an incorrect action type.
        """
        if self._observation is None or self._scenario is None:
            raise RuntimeError("Call reset() before step().")
        if self._observation.is_done:
            raise RuntimeError("Episode is already finished. Call reset() to start a new one.")

        expected_action: ActionType = self._scenario["expected_action"]
        expected_disc: list[DiscrepancyType] = self._scenario["expected_discrepancies"]

        detected = self._detect_discrepancies()
        reward, info = self._evaluate(action, expected_action, expected_disc, detected)

        self._observation = InvoiceObservation(
            episode_id=self._observation.episode_id,
            task_id=self._observation.task_id,
            step=self._observation.step + 1,
            invoice=self._observation.invoice,
            purchase_order=self._observation.purchase_order,
            goods_received_note=self._observation.goods_received_note,
            discrepancies=detected,
            is_done=True,
            reward=reward,
            info=info,
        )
        return self._observation

    def state(self) -> InvoiceObservation:
        """Return the current observation without advancing the episode."""
        if self._observation is None:
            raise RuntimeError("Call reset() before state().")
        return self._observation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_discrepancies(self) -> list[Discrepancy]:
        """Automatically detect discrepancies in the current scenario."""
        assert self._scenario is not None
        discrepancies: list[Discrepancy] = []
        invoice: Invoice = self._scenario["invoice"]
        po: PurchaseOrder | None = self._scenario.get("purchase_order")
        grn: GoodsReceivedNote | None = self._scenario.get("goods_received_note")

        if po is None:
            discrepancies.append(
                Discrepancy(
                    discrepancy_type=DiscrepancyType.PO_NOT_FOUND,
                    field="po_reference",
                    invoice_value=invoice.po_reference,
                    expected_value=None,
                    description="No matching Purchase Order found for this invoice.",
                )
            )
            return discrepancies

        # Vendor name mismatch (case-insensitive + strip punctuation)
        def _normalise(name: str) -> str:
            return "".join(c.lower() for c in name if c.isalnum() or c.isspace()).strip()

        if _normalise(invoice.vendor_name) != _normalise(po.vendor_name):
            discrepancies.append(
                Discrepancy(
                    discrepancy_type=DiscrepancyType.VENDOR_NAME_MISMATCH,
                    field="vendor_name",
                    invoice_value=invoice.vendor_name,
                    expected_value=po.vendor_name,
                    description=(
                        f"Vendor name on invoice ('{invoice.vendor_name}') does not "
                        f"match PO ('{po.vendor_name}')."
                    ),
                )
            )

        # Build a map of PO items by normalised description
        po_items = {
            " ".join(item.description.lower().split()): item
            for item in po.line_items
        }
        grn_items = (
            {
                " ".join(item.description.lower().split()): item
                for item in grn.items_received
            }
            if grn
            else {}
        )
        inv_descriptions = {
            " ".join(item.description.lower().split()) for item in invoice.line_items
        }

        for inv_item in invoice.line_items:
            key = " ".join(inv_item.description.lower().split())
            # Check for extra charges not in PO (fuzzy: look for any word overlap)
            matched_key = self._fuzzy_match_key(key, po_items.keys())
            if matched_key is None:
                discrepancies.append(
                    Discrepancy(
                        discrepancy_type=DiscrepancyType.EXTRA_CHARGE,
                        field="line_items",
                        invoice_value=inv_item.description,
                        expected_value=None,
                        description=(
                            f"Line item '{inv_item.description}' on invoice has "
                            "no corresponding entry in the PO."
                        ),
                    )
                )
                continue

            po_item = po_items[matched_key]

            # Price mismatch
            if inv_item.unit_price != po_item.unit_price:
                discrepancies.append(
                    Discrepancy(
                        discrepancy_type=DiscrepancyType.PRICE_MISMATCH,
                        field=f"unit_price[{inv_item.description}]",
                        invoice_value=str(inv_item.unit_price),
                        expected_value=str(po_item.unit_price),
                        description=(
                            f"Unit price for '{inv_item.description}' is "
                            f"{inv_item.unit_price} on invoice but {po_item.unit_price} on PO."
                        ),
                    )
                )

            # Quantity mismatch against GRN
            if grn_items:
                grn_key = self._fuzzy_match_key(key, grn_items.keys())
                if grn_key is not None:
                    grn_item = grn_items[grn_key]
                    if inv_item.quantity != grn_item.quantity:
                        discrepancies.append(
                            Discrepancy(
                                discrepancy_type=DiscrepancyType.QUANTITY_MISMATCH,
                                field=f"quantity[{inv_item.description}]",
                                invoice_value=str(inv_item.quantity),
                                expected_value=str(grn_item.quantity),
                                description=(
                                    f"Quantity for '{inv_item.description}' is "
                                    f"{inv_item.quantity} on invoice but only "
                                    f"{grn_item.quantity} was received (GRN)."
                                ),
                            )
                        )

        # Check for PO items missing from invoice
        for po_key, po_item in po_items.items():
            if self._fuzzy_match_key(po_key, inv_descriptions) is None:
                discrepancies.append(
                    Discrepancy(
                        discrepancy_type=DiscrepancyType.MISSING_LINE_ITEM,
                        field="line_items",
                        invoice_value=None,
                        expected_value=po_item.description,
                        description=(
                            f"PO line item '{po_item.description}' is missing "
                            "from the invoice."
                        ),
                    )
                )

        return discrepancies

    @staticmethod
    def _fuzzy_match_key(key: str, candidates: Any) -> str | None:
        """Return the best candidate key that shares the most words with *key*, or None."""
        key_words = set(key.split())
        best: str | None = None
        best_score = 0
        for candidate in candidates:
            cand_words = set(candidate.split())
            score = len(key_words & cand_words)
            if score > best_score:
                best_score = score
                best = candidate
        # Require at least one shared word to count as a match
        return best if best_score > 0 else None

    @staticmethod
    def _evaluate(
        action: InvoiceAction,
        expected_action: ActionType,
        expected_disc: list[DiscrepancyType],
        detected_disc: list[Discrepancy],
    ) -> tuple[float, dict[str, Any]]:
        """Return (reward, info) for the submitted action."""
        detected_types = {d.discrepancy_type for d in detected_disc}
        flagged_types = set(action.discrepancy_flags)
        expected_set = set(expected_disc)

        action_correct = action.action_type == expected_action

        if not action_correct:
            return _REWARD_WRONG, {
                "result": "incorrect",
                "expected_action": expected_action,
                "submitted_action": action.action_type,
            }

        # Action is correct – check discrepancy completeness
        if expected_set:
            correctly_flagged = flagged_types & expected_set
            if correctly_flagged == expected_set:
                reward = _REWARD_CORRECT
                result = "correct"
            else:
                reward = _REWARD_PARTIAL
                result = "partial"
        else:
            # No discrepancies expected; perfect if agent flagged none
            reward = _REWARD_CORRECT if not flagged_types else _REWARD_PARTIAL
            result = "correct" if not flagged_types else "partial"

        return reward, {
            "result": result,
            "expected_action": expected_action,
            "submitted_action": action.action_type,
            "expected_discrepancies": [d.value for d in expected_set],
            "flagged_discrepancies": [d.value for d in flagged_types],
            "detected_discrepancies": [d.value for d in detected_types],
        }


# ---------------------------------------------------------------------------
# Module-level singleton used by the FastAPI routes
# ---------------------------------------------------------------------------

env = InvoiceReconciliationEnv()
