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
            invoice_date="2025-03-10",
            due_date="2025-04-09",
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
            total_amount=2200.00,
            currency="USD",
            items_billed={"Office Chair": 10, "Desk Lamp": 20},
            extracted_po_ref="PO-5001",
            raw_text_content=(
                "INVOICE\nInvoice No: INV-1001\nDate: 2025-03-10\nDue: 2025-04-09\n"
                "Vendor: Acme Supplies Ltd.\nPO Reference: PO-5001\n\n"
                "Office Chair x10 @ $150.00 = $1,500.00\n"
                "Desk Lamp x20 @ $25.00 = $500.00\n"
                "Subtotal: $2,000.00  Tax (10%): $200.00  Total: $2,200.00\n"
                "Payment Terms: Net 30"
            ),
            discrepancy_details={},
        ),
        "candidate_pos": [
            PurchaseOrder(
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
            )
        ],
        "grn_log": [
            GoodsReceivedNote(
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
            )
        ],
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
            vendor_name="ACME Supplies Ltd",  # capitalisation differs — vendor_name_mismatch
            invoice_date="2025-03-15",
            due_date="2025-04-14",
            line_items=[
                LineItem(
                    description="Ergonomic Office Chair",  # slight wording change
                    quantity=Decimal("5"),
                    unit_price=Decimal("152.00"),  # $2 over PO price — price_mismatch
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
            total_amount=1133.00,
            currency="USD",
            items_billed={"Ergonomic Office Chair": 5, "USB Hub 4-Port": 15},
            extracted_po_ref=None,  # PO ref buried in raw text — forces agent to parse
            raw_text_content=(
                "Invoice # INV-2002  |  Date: 15 March 2025  |  Due: 14 April 2025\n"
                "From: ACME Supplies Ltd (note: formerly Acme Supplies Ltd.)\n"
                "Re: Purchase Order ref. PO-5002\n\n"
                "Ergonomic Office Chair (5 units) ........... $152.00/ea = $760.00\n"
                "USB Hub 4-Port        (15 units) ........... $18.00/ea  = $270.00\n"
                "                                            Subtotal    $1,030.00\n"
                "                                            Tax  10%    $  103.00\n"
                "                                            TOTAL       $1,133.00\n"
                "Terms: Net 30. Please remit to bank account on file."
            ),
            discrepancy_details={
                "vendor_name_mismatch": {"invoice": "ACME Supplies Ltd", "po": "Acme Supplies Ltd."},
                "price_mismatch": {"item": "Ergonomic Office Chair", "invoice_price": 152.00, "po_price": 150.00},
            },
        ),
        "candidate_pos": [
            PurchaseOrder(
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
            )
        ],
        "grn_log": [
            GoodsReceivedNote(
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
            )
        ],
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
            invoice_date="2025-03-20",
            due_date="2025-04-19",
            line_items=[
                LineItem(
                    description="Laptop Model X",
                    quantity=Decimal("10"),
                    unit_price=Decimal("1200.00"),  # PO has $1100 — price_mismatch
                    total=Decimal("12000.00"),
                ),
                LineItem(
                    description="Wireless Mouse",
                    quantity=Decimal("10"),  # only 8 delivered — quantity_mismatch
                    unit_price=Decimal("35.00"),
                    total=Decimal("350.00"),
                ),
                LineItem(
                    description="Extended Warranty",  # not in PO — extra_charge
                    quantity=Decimal("10"),
                    unit_price=Decimal("50.00"),
                    total=Decimal("500.00"),
                ),
            ],
            subtotal=Decimal("12850.00"),
            tax=Decimal("1285.00"),
            total_amount=14135.00,
            currency="USD",
            items_billed={"Laptop Model X": 10, "Wireless Mouse": 10, "Extended Warranty": 10},
            extracted_po_ref="PO-5003",
            raw_text_content=(
                "TAX INVOICE\nInvoice: INV-3003  Date: 20-Mar-2025  Due: 19-Apr-2025\n"
                "Supplier: Global Tech Solutions Inc.\n"
                "Bill To: Buyer Corp   PO#: PO-5003\n\n"
                "1. Laptop Model X        qty=10  unit=$1,200.00  line=$12,000.00\n"
                "   ** Note: price adjusted from $1,100 due to component cost increase **\n"
                "2. Wireless Mouse        qty=10  unit=$35.00     line=$350.00\n"
                "   (GRN shows only 8 units received as of 2025-03-18)\n"
                "3. Extended Warranty     qty=10  unit=$50.00     line=$500.00\n"
                "   ** Not listed in original PO; added post-shipment **\n\n"
                "Subtotal: $12,850.00  |  Tax (10%): $1,285.00  |  TOTAL DUE: $14,135.00\n"
                "Payment Terms: Net 30"
            ),
            discrepancy_details={
                "price_mismatch": {"item": "Laptop Model X", "invoice_price": 1200.00, "po_price": 1100.00},
                "quantity_mismatch": {"item": "Wireless Mouse", "invoiced": 10, "received": 8},
                "extra_charge": {"item": "Extended Warranty", "po_entry": None},
            },
        ),
        "candidate_pos": [
            PurchaseOrder(
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
            )
        ],
        "grn_log": [
            GoodsReceivedNote(
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
            )
        ],
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
        self.current_ground_truth: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public OpenEnv API
    # ------------------------------------------------------------------

    def reset(self, task_id: str) -> InvoiceObservation:
        """Initialise a new episode for *task_id* and return the first observation."""
        if task_id in _SCENARIOS:
            self._scenario = _SCENARIOS[task_id]
        elif task_id.startswith(("easy_", "medium_", "hard_")):
            difficulty = task_id.split("_")[0]
            from server.data_generator import InvoiceDataGenerator
            
            seed_str = "".join(filter(str.isdigit, task_id))
            seed = int(seed_str) if seed_str else None
            
            gen = InvoiceDataGenerator(seed=seed)
            invoice, pos, grns, true_po_id, decision_str, disc_details = gen.generate_task_data(difficulty)
            
            decision_map = {
                "pay": ActionType.APPROVE,
                "hold": ActionType.FLAG_DISCREPANCY,
                "flag": ActionType.REJECT
            }
            expected_action = decision_map.get(decision_str, ActionType.ESCALATE)
            
            expected_discrepancies = []
            if "amount_diff" in disc_details or "major_price_mismatch" in disc_details or "price_mismatch" in disc_details:
                expected_discrepancies.append(DiscrepancyType.PRICE_MISMATCH)
            if "vendor_name_variation" in disc_details or "incorrect_vendor" in disc_details:
                expected_discrepancies.append(DiscrepancyType.VENDOR_NAME_MISMATCH)
            if "quantity_mismatch" in disc_details or "quantity_billed_over" in disc_details:
                expected_discrepancies.append(DiscrepancyType.QUANTITY_MISMATCH)
            if "item_added_to_invoice" in disc_details:
                expected_discrepancies.append(DiscrepancyType.EXTRA_CHARGE)
            if "item_removed_from_invoice" in disc_details:
                expected_discrepancies.append(DiscrepancyType.MISSING_LINE_ITEM)
                
            self._scenario = {
                "description": f"Dynamic {difficulty} task: {task_id}",
                "invoice": invoice,
                "candidate_pos": pos,
                "grn_log": grns,
                "expected_action": expected_action,
                "expected_discrepancies": expected_discrepancies
            }
            # Add ground truth for precise evaluation
            self.current_ground_truth = {
                "true_po_id": true_po_id,
                "correct_decision": decision_str,
                "discrepancy_details": disc_details
            }
        else:
            raise ValueError(
                f"Unknown task_id '{task_id}'. "
                f"Valid tasks: easy_N, medium_N, hard_N or {list(_SCENARIOS.keys())}"
            )

        episode_id = str(uuid.uuid4())

        self._observation = InvoiceObservation(
            episode_id=episode_id,
            task_id=task_id,
            step=0,
            invoice=self._scenario["invoice"],
            candidate_pos=self._scenario.get("candidate_pos", []),
            grn_log=self._scenario.get("grn_log", []),
            discrepancies=[],
            is_done=False,
            reward=0.0,
            info={"description": self._scenario["description"]},
        )
        return self._observation

    def step(self, action: InvoiceAction) -> InvoiceReward:
        """Process *action* and return the detailed reward."""
        if self._observation is None or self._scenario is None:
            raise RuntimeError("Call reset() before step().")
        if self._observation.is_done:
            raise RuntimeError("Episode is already finished. Call reset() to start a new one.")

        # If it's a static scenario, ground truth isn't fully structured yet, so we bridge it
        if self.current_ground_truth is None:
            # Fallback for static scenarios
            disc_types = {d.value for d in self._scenario.get("expected_discrepancies", [])}
            self.current_ground_truth = {
                "true_po_id": self._scenario.get("candidate_pos", [None])[0].po_id if self._scenario.get("candidate_pos") else None,
                "correct_decision": self._scenario["expected_action"].value if isinstance(self._scenario["expected_action"], ActionType) else self._scenario["expected_action"],
                "discrepancy_details": {d: {} for d in disc_types}
            }

        # --- REWARD CALCULATION LOGIC (0.0 to 1.0) ---
        score = 0.0
        reason_parts = []
        gt = self.current_ground_truth

        # 1. Correct Action Type (0.5 points)
        # Map our ActionType to the decision strings (pay/hold/flag)
        decision_map = {
            ActionType.APPROVE: "pay",
            ActionType.FLAG_DISCREPANCY: "hold",
            ActionType.REJECT: "flag"
        }
        gt_decision = gt["correct_decision"]
        agent_decision = decision_map.get(action.action_type, "other")

        correct_decision_made = (agent_decision == gt_decision)
        if correct_decision_made:
            score += 0.5
            reason_parts.append("Correct overall decision (0.5 pts).")
        else:
            reason_parts.append(f"Incorrect decision: Agent chose '{agent_decision}', expected '{gt_decision}' (0.0 pts).")

        # 2. Correct PO Linkage (0.2 points)
        correct_po_identified = (action.matched_po_id == gt["true_po_id"])
        if correct_po_identified:
            score += 0.2
            reason_parts.append("Correct PO identified (0.2 pts).")
        else:
            reason_parts.append(f"Incorrect PO: Agent linked '{action.matched_po_id}', expected '{gt['true_po_id']}' (0.0 pts).")

        # 3. Discrepancy Detection & Detailed Reasoning (0.3 points)
        discrepancy_correctly_noted = False
        disc_details = gt["discrepancy_details"]
        if disc_details:
            # Check if agent's reasoning or discrepancies flagged indicate awareness
            reasoning = action.reasoning.lower() if action.reasoning else ""
            found_match = False
            for d_name in disc_details.keys():
                if d_name.replace('_', ' ') in reasoning or d_name in reasoning:
                    found_match = True
                    break
            
            # Also check if they used specific discrepancy flags
            if not found_match and action.discrepancy_flags:
                # If they flagged anything and there are discrepancies, we give partial credit
                # But here we stick to the 0.3 all-or-nothing for simplicity
                found_match = True 

            if found_match:
                score += 0.3
                discrepancy_correctly_noted = True
                reason_parts.append("Relevant discrepancy noted in reasoning/flags (0.3 pts).")
            else:
                reason_parts.append("Discrepancies present, but not clearly identified by agent (0.0 pts).")
        else:
            # No discrepancies
            if not action.discrepancy_flags and (not action.reasoning or "no discrepancy" in action.reasoning.lower()):
                score += 0.3
                discrepancy_correctly_noted = True
                reason_parts.append("Correctly noted no discrepancy (0.3 pts).")
            else:
                reason_parts.append("No discrepancies present, but agent flagged something or didn't confirm clean status (0.0 pts).")

        final_score = round(min(score, 1.0), 2)
        from server.models import InvoiceReward
        
        # Mark episode as done
        self._observation.is_done = True
        self._observation.reward = final_score

        return InvoiceReward(
            score=final_score,
            correct_decision_made=correct_decision_made,
            correct_po_identified=correct_po_identified,
            discrepancy_correctly_noted=discrepancy_correctly_noted,
            reason=" | ".join(reason_parts)
        )

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
        candidate_pos: list[PurchaseOrder] = self._scenario.get("candidate_pos", [])
        grn_log: list[GoodsReceivedNote] = self._scenario.get("grn_log", [])

        po: PurchaseOrder | None = candidate_pos[0] if candidate_pos else None
        grn: GoodsReceivedNote | None = grn_log[0] if grn_log else None

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
