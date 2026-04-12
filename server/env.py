"""OpenEnv environment logic for Invoice Reconciliation – multi-step edition.

Episode stages & rewards
------------------------
  1. select_po          Correct PO chosen from candidates.                  +0.20
                        Wrong-but-valid PO chosen (stage still advances).   −0.10
  2. compare_items      All 3 booleans correct for a line item.             +0.10 / item
                        At least one boolean correct.                        +0.04 / item
  3. flag_discrepancies Valid discrepancy flag (in ground truth).            +0.10 / flag
                        Spurious flag (not in ground truth).                 −0.05 / flag
                        Duplicate flag.                                       0.00
  4. final_decision     Correct decision type.                               +0.30
                        WRONG decision type.                                 −0.60
                        Discrepancy coverage (prorated 0–0.10).             +0.10 max
  Episode incomplete    max_steps reached before final_decision.            −0.10 penalty

Maximum possible reward (perfect agent, hard task): ~1.20
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from server.models import (
    CompareItemAction,
    Discrepancy,
    DiscrepancyType,
    FinalDecisionAction,
    FlagDiscrepancyAction,
    GoodsReceivedNote,
    Invoice,
    InvoiceAction,
    InvoiceObservation,
    LineItem,
    PurchaseOrder,
    SelectPOAction,
)

# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

_SCENARIOS: dict[str, dict[str, Any]] = {
    "easy-exact-match": {
        "description": "Invoice amounts and line items exactly match the PO.",
        "invoice": Invoice(
            invoice_id="INV-1001",
            vendor_name="Acme Supplies Ltd.",
            invoice_date=date(2025, 3, 10),
            line_items=[
                LineItem(description="Office Chair",  quantity=Decimal("10"),
                         unit_price=Decimal("150.00"), total=Decimal("1500.00")),
                LineItem(description="Desk Lamp",     quantity=Decimal("20"),
                         unit_price=Decimal("25.00"),  total=Decimal("500.00")),
            ],
            subtotal=Decimal("2000.00"),
            tax=Decimal("200.00"),
            total_amount=Decimal("2200.00"),
            currency="USD",
            po_reference="PO-5001",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-5001",
                vendor_name="Acme Supplies Ltd.",
                issue_date=date(2025, 3, 1),
                line_items=[
                    LineItem(description="Office Chair", quantity=Decimal("10"),
                             unit_price=Decimal("150.00"), total=Decimal("1500.00")),
                    LineItem(description="Desk Lamp",    quantity=Decimal("20"),
                             unit_price=Decimal("25.00"),  total=Decimal("500.00")),
                ],
                total_amount=Decimal("2000.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
            # Distractor PO from a different vendor
            PurchaseOrder(
                po_id="PO-5099",
                vendor_name="TechMart Corp.",
                issue_date=date(2025, 2, 15),
                line_items=[
                    LineItem(description="Monitor Stand", quantity=Decimal("5"),
                             unit_price=Decimal("40.00"),  total=Decimal("200.00")),
                ],
                total_amount=Decimal("200.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-5001",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-3001",
            po_id="PO-5001",
            received_date=date(2025, 3, 8),
            items_received=[
                LineItem(description="Office Chair", quantity=Decimal("10"),
                         unit_price=Decimal("150.00"), total=Decimal("1500.00")),
                LineItem(description="Desk Lamp",    quantity=Decimal("20"),
                         unit_price=Decimal("25.00"),  total=Decimal("500.00")),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "approve",
        "expected_discrepancies": [],
        # max_reward = 0.20 (PO) + 2×0.10 (items) + 0 (no flags) + 0.30+0.10 (decision)
        "max_reward": 0.80,
    },

    "medium-fuzzy-match": {
        "description": (
            "Vendor name has minor text variation and one unit price differs "
            "by a small rounding amount, requiring fuzzy matching."
        ),
        "invoice": Invoice(
            invoice_id="INV-2002",
            vendor_name="ACME Supplies Ltd",          # capitalisation differs
            invoice_date=date(2025, 3, 15),
            line_items=[
                LineItem(description="Ergonomic Office Chair",  # slight wording
                         quantity=Decimal("5"),
                         unit_price=Decimal("152.00"),          # $2 over PO
                         total=Decimal("760.00")),
                LineItem(description="USB Hub 4-Port",
                         quantity=Decimal("15"),
                         unit_price=Decimal("18.00"),
                         total=Decimal("270.00")),
            ],
            subtotal=Decimal("1030.00"),
            tax=Decimal("103.00"),
            total_amount=Decimal("1133.00"),
            currency="USD",
            po_reference="PO-5002",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-5002",
                vendor_name="Acme Supplies Ltd.",
                issue_date=date(2025, 3, 5),
                line_items=[
                    LineItem(description="Office Chair",
                             quantity=Decimal("5"),
                             unit_price=Decimal("150.00"),
                             total=Decimal("750.00")),
                    LineItem(description="USB Hub 4-Port",
                             quantity=Decimal("15"),
                             unit_price=Decimal("18.00"),
                             total=Decimal("270.00")),
                ],
                total_amount=Decimal("1020.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
            PurchaseOrder(
                po_id="PO-5098",
                vendor_name="Office World Inc.",
                issue_date=date(2025, 3, 2),
                line_items=[
                    LineItem(description="Ergonomic Chair",
                             quantity=Decimal("3"),
                             unit_price=Decimal("180.00"),
                             total=Decimal("540.00")),
                ],
                total_amount=Decimal("540.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-5002",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-3002",
            po_id="PO-5002",
            received_date=date(2025, 3, 13),
            items_received=[
                LineItem(description="Office Chair",
                         quantity=Decimal("5"),
                         unit_price=Decimal("150.00"),
                         total=Decimal("750.00")),
                LineItem(description="USB Hub 4-Port",
                         quantity=Decimal("15"),
                         unit_price=Decimal("18.00"),
                         total=Decimal("270.00")),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "flag_discrepancy",
        "expected_discrepancies": [
            DiscrepancyType.VENDOR_NAME_MISMATCH,
            DiscrepancyType.PRICE_MISMATCH,
        ],
        # max_reward = 0.20 (PO) + 2×0.10 (items) + 2×0.10 (flags) + 0.30+0.10 (decision)
        "max_reward": 1.00,
    },

    "hard-discrepancy-detection": {
        "description": (
            "Multiple discrepancies: partial delivery, price mismatch on a "
            "high-value item, and an extra charge not present in the PO."
        ),
        "invoice": Invoice(
            invoice_id="INV-3003",
            vendor_name="Global Tech Solutions Inc.",
            invoice_date=date(2025, 3, 20),
            line_items=[
                LineItem(description="Laptop Model X",
                         quantity=Decimal("10"),
                         unit_price=Decimal("1200.00"),   # PO: $1100
                         total=Decimal("12000.00")),
                LineItem(description="Wireless Mouse",
                         quantity=Decimal("10"),           # GRN: 8 received
                         unit_price=Decimal("35.00"),
                         total=Decimal("350.00")),
                LineItem(description="Extended Warranty",  # not in PO
                         quantity=Decimal("10"),
                         unit_price=Decimal("50.00"),
                         total=Decimal("500.00")),
            ],
            subtotal=Decimal("12850.00"),
            tax=Decimal("1285.00"),
            total_amount=Decimal("14135.00"),
            currency="USD",
            po_reference="PO-5003",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-5003",
                vendor_name="Global Tech Solutions Inc.",
                issue_date=date(2025, 3, 10),
                line_items=[
                    LineItem(description="Laptop Model X",
                             quantity=Decimal("10"),
                             unit_price=Decimal("1100.00"),
                             total=Decimal("11000.00")),
                    LineItem(description="Wireless Mouse",
                             quantity=Decimal("10"),
                             unit_price=Decimal("35.00"),
                             total=Decimal("350.00")),
                ],
                total_amount=Decimal("11350.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
            PurchaseOrder(
                po_id="PO-5097",
                vendor_name="Global Tech Solutions",      # slightly different
                issue_date=date(2025, 3, 8),
                line_items=[
                    LineItem(description="Laptop Model Y",
                             quantity=Decimal("5"),
                             unit_price=Decimal("950.00"),
                             total=Decimal("4750.00")),
                ],
                total_amount=Decimal("4750.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-5003",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-3003",
            po_id="PO-5003",
            received_date=date(2025, 3, 18),
            items_received=[
                LineItem(description="Laptop Model X",
                         quantity=Decimal("10"),
                         unit_price=Decimal("1100.00"),
                         total=Decimal("11000.00")),
                LineItem(description="Wireless Mouse",
                         quantity=Decimal("8"),    # only 8 received
                         unit_price=Decimal("35.00"),
                         total=Decimal("280.00")),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "reject",
        "expected_discrepancies": [
            DiscrepancyType.PRICE_MISMATCH,
            DiscrepancyType.QUANTITY_MISMATCH,
            DiscrepancyType.EXTRA_CHARGE,
        ],
        # max_reward = 0.20 (PO) + 3×0.10 (items) + 3×0.10 (flags) + 0.30+0.10 (decision)
        "max_reward": 1.20,
    },

    # ── NEW: Ambiguous split invoice ────────────────────────────────────────
    # Two POs both partially cover the invoice. No po_reference on the invoice.
    # Agent must reason about which PO is the primary match.
    # The correct PO (PO-6001) covers the main hardware items with exact vendor
    # name, but still has 3 real discrepancies vs the invoice.
    # PO-6002 is a tempting decoy: different vendor name variant, covers
    # two items that overlap but at wrong quantities / scope.
    "ambiguous-split-invoice": {
        "description": (
            "No PO reference on the invoice. Two candidate POs partly overlap. "
            "Agent must identify the primary PO through reasoning, then detect "
            "price mismatch, quantity shortfall, and an extra charge."
        ),
        "invoice": Invoice(
            invoice_id="INV-4004",
            vendor_name="SkyBridge Solutions Ltd.",
            invoice_date=date(2025, 4, 1),
            line_items=[
                LineItem(
                    description="Network Switch 24-Port",
                    quantity=Decimal("5"),
                    unit_price=Decimal("280.00"),
                    total=Decimal("1400.00"),
                ),
                LineItem(
                    description="CAT6 Cable Bundle",
                    quantity=Decimal("50"),
                    unit_price=Decimal("12.00"),   # PO-6001 has $10 → price_mismatch
                    total=Decimal("600.00"),
                ),
                LineItem(
                    description="Installation Service",  # not in PO-6001 → extra_charge
                    quantity=Decimal("1"),
                    unit_price=Decimal("800.00"),
                    total=Decimal("800.00"),
                ),
            ],
            subtotal=Decimal("2800.00"),
            tax=Decimal("280.00"),
            total_amount=Decimal("3080.00"),
            currency="USD",
            po_reference=None,   # ← KEY: no reference — agent must reason
        ),
        "available_pos": [
            # PRIMARY PO — exact vendor, covers main hardware items
            PurchaseOrder(
                po_id="PO-6001",
                vendor_name="SkyBridge Solutions Ltd.",
                issue_date=date(2025, 3, 20),
                line_items=[
                    LineItem(
                        description="Network Switch 24-Port",
                        quantity=Decimal("5"),
                        unit_price=Decimal("280.00"),
                        total=Decimal("1400.00"),
                    ),
                    LineItem(
                        description="CAT6 Cable Bundle",
                        quantity=Decimal("50"),
                        unit_price=Decimal("10.00"),  # $2 cheaper than invoice
                        total=Decimal("500.00"),
                    ),
                ],
                total_amount=Decimal("1900.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
            # DECOY PO — fuzzy vendor name, covers services + cables but at
            # a different quantity, tempting but ultimately the wrong primary PO
            PurchaseOrder(
                po_id="PO-6002",
                vendor_name="Skybridge solutions",   # different casing + no punctuation
                issue_date=date(2025, 3, 18),
                line_items=[
                    LineItem(
                        description="CAT6 Cable Bundle",
                        quantity=Decimal("30"),       # only 30 in this PO vs 50 invoiced
                        unit_price=Decimal("12.00"),
                        total=Decimal("360.00"),
                    ),
                    LineItem(
                        description="Installation Service",
                        quantity=Decimal("1"),
                        unit_price=Decimal("800.00"),
                        total=Decimal("800.00"),
                    ),
                ],
                total_amount=Decimal("1160.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-6001",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-4004",
            po_id="PO-6001",
            received_date=date(2025, 3, 30),
            items_received=[
                LineItem(
                    description="Network Switch 24-Port",
                    quantity=Decimal("5"),
                    unit_price=Decimal("280.00"),
                    total=Decimal("1400.00"),
                ),
                LineItem(
                    description="CAT6 Cable Bundle",
                    quantity=Decimal("45"),           # 45 received vs 50 invoiced → qty_mismatch
                    unit_price=Decimal("10.00"),
                    total=Decimal("450.00"),
                ),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "reject",
        "expected_discrepancies": [
            DiscrepancyType.PRICE_MISMATCH,      # CAT6: invoice $12 vs PO-6001 $10
            DiscrepancyType.QUANTITY_MISMATCH,   # CAT6: invoiced 50, GRN received 45
            DiscrepancyType.EXTRA_CHARGE,        # Installation Service not in PO-6001
        ],
        # max_reward = 0.20 (PO) + 3×0.10 (items) + 3×0.10 (flags) + 0.30+0.10 (decision)
        "max_reward": 1.20,
    },

    # ── NEW: Compliance SOC2 vendor task ────────────────────────────────────
    # Tests whether the agent catches inflated pricing and unauthorized fees
    # from a non-SOC2 vendor. Real-world: SOC2 violations cost $250K+ in
    # audit penalties (Gartner 2024).
    "compliance-soc2-vendor": {
        "description": (
            "Invoice from a non-SOC2 vendor with inflated cloud storage pricing "
            "and an unauthorized 'SOC2 Audit Fee' line item not in the PO. "
            "Company policy requires vendors over $5K to be SOC2 certified. "
            "Agent must detect price overcharge and extra charge, then REJECT."
        ),
        "invoice": Invoice(
            invoice_id="INV-5001",
            vendor_name="CheapCorp LLC",
            invoice_date=date(2025, 4, 5),
            line_items=[
                LineItem(description="Cloud Storage Annual",
                         quantity=Decimal("12"),
                         unit_price=Decimal("500.00"),     # PO: $450 → price_mismatch
                         total=Decimal("6000.00")),
                LineItem(description="SOC2 Compliance Audit Fee",  # not in PO → extra_charge
                         quantity=Decimal("1"),
                         unit_price=Decimal("1200.00"),
                         total=Decimal("1200.00")),
            ],
            subtotal=Decimal("7200.00"),
            tax=Decimal("720.00"),
            total_amount=Decimal("7920.00"),
            currency="USD",
            po_reference="PO-7001",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-7001",
                vendor_name="CheapCorp LLC",
                issue_date=date(2025, 3, 20),
                line_items=[
                    LineItem(description="Cloud Storage Annual",
                             quantity=Decimal("12"),
                             unit_price=Decimal("450.00"),   # $50 less than invoice
                             total=Decimal("5400.00")),
                ],
                total_amount=Decimal("5400.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
            PurchaseOrder(
                po_id="PO-7002",
                vendor_name="SecureVault Inc.",
                issue_date=date(2025, 3, 18),
                line_items=[
                    LineItem(description="Cloud Storage Annual",
                             quantity=Decimal("10"),
                             unit_price=Decimal("650.00"),
                             total=Decimal("6500.00")),
                ],
                total_amount=Decimal("6500.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-7001",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-5001",
            po_id="PO-7001",
            received_date=date(2025, 4, 1),
            items_received=[
                LineItem(description="Cloud Storage Annual",
                         quantity=Decimal("12"),
                         unit_price=Decimal("450.00"),
                         total=Decimal("5400.00")),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "reject",
        "expected_discrepancies": [
            DiscrepancyType.PRICE_MISMATCH,       # $500 vs $450 per unit
            DiscrepancyType.EXTRA_CHARGE,          # SOC2 Audit Fee not in PO
        ],
        # max_reward = 0.20 (PO) + 2×0.10 (items) + 2×0.10 (flags) + 0.30+0.10 (decision)
        "max_reward": 1.00,
        "compliance_rule": "SOC2_REQUIRED_FOR_ORDERS_OVER_5000",
    },

    # ── NEW: Multi-currency compliance task ─────────────────────────────────
    # EUR invoice against USD PO — FX policy requires treasury approval.
    # Real-world: currency mismatch errors cause $50K+ FX losses per incident.
    "multi-currency-compliance": {
        "description": (
            "EUR-denominated invoice against a USD Purchase Order creates an "
            "$800 FX-induced price discrepancy. Company FX policy requires "
            "treasury approval for cross-currency invoices. Agent must detect "
            "the price gap and FLAG for review."
        ),
        "invoice": Invoice(
            invoice_id="INV-5002",
            vendor_name="EuroTech GmbH",
            invoice_date=date(2025, 4, 10),
            line_items=[
                LineItem(description="Enterprise Software License",
                         quantity=Decimal("1"),
                         unit_price=Decimal("10800.00"),  # EUR→USD spot vs PO $10000
                         total=Decimal("10800.00")),
                LineItem(description="Implementation Support",
                         quantity=Decimal("1"),
                         unit_price=Decimal("2500.00"),
                         total=Decimal("2500.00")),
            ],
            subtotal=Decimal("13300.00"),
            tax=Decimal("1330.00"),
            total_amount=Decimal("14630.00"),
            currency="EUR",
            po_reference="PO-7003",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-7003",
                vendor_name="EuroTech GmbH",
                issue_date=date(2025, 3, 25),
                line_items=[
                    LineItem(description="Enterprise Software License",
                             quantity=Decimal("1"),
                             unit_price=Decimal("10000.00"),
                             total=Decimal("10000.00")),
                    LineItem(description="Implementation Support",
                             quantity=Decimal("1"),
                             unit_price=Decimal("2500.00"),
                             total=Decimal("2500.00")),
                ],
                total_amount=Decimal("12500.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
            PurchaseOrder(
                po_id="PO-7099",
                vendor_name="TechMax Solutions",
                issue_date=date(2025, 3, 15),
                line_items=[
                    LineItem(description="Software License Basic",
                             quantity=Decimal("5"),
                             unit_price=Decimal("1500.00"),
                             total=Decimal("7500.00")),
                ],
                total_amount=Decimal("7500.00"),
                currency="USD",
                approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-7003",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-5002",
            po_id="PO-7003",
            received_date=date(2025, 4, 8),
            items_received=[
                LineItem(description="Enterprise Software License",
                         quantity=Decimal("1"),
                         unit_price=Decimal("10000.00"),
                         total=Decimal("10000.00")),
                LineItem(description="Implementation Support",
                         quantity=Decimal("1"),
                         unit_price=Decimal("2500.00"),
                         total=Decimal("2500.00")),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "flag_discrepancy",
        "expected_discrepancies": [
            DiscrepancyType.PRICE_MISMATCH,       # $10800 vs $10000 (FX gap)
        ],
        # max_reward = 0.20 (PO) + 2×0.10 (items) + 1×0.10 (flag) + 0.30+0.10 (decision)
        "max_reward": 0.90,
        "compliance_rule": "FX_POLICY_REQUIRES_TREASURY_APPROVAL",
    },

    "vat-reverse-charge": {
        "description": "EU B2B invoice must apply VAT reverse charge per Directive 2006/112/EC. Agent must flag if vendor charged VAT.",
        "invoice": Invoice(
            invoice_id="INV-6001", vendor_name="EuroVendor GmbH", invoice_date=date(2025, 4, 5),
            line_items=[LineItem(description="Consulting", quantity=Decimal("1"),
                       unit_price=Decimal("10000.00"), total=Decimal("10000.00"))],
            subtotal=Decimal("10000.00"), tax=Decimal("2000.00"), total_amount=Decimal("12000.00"),
            currency="EUR", po_reference="PO-8001",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-8001", vendor_name="EuroVendor GmbH", issue_date=date(2025, 3, 28),
                line_items=[LineItem(description="Consulting", quantity=Decimal("1"),
                           unit_price=Decimal("10000.00"), total=Decimal("10000.00"))],
                total_amount=Decimal("10000.00"), currency="EUR", approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-8001",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-6001", po_id="PO-8001", received_date=date(2025, 4, 3),
            items_received=[LineItem(description="Consulting", quantity=Decimal("1"),
                           unit_price=Decimal("10000.00"), total=Decimal("10000.00"))],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "flag_discrepancy",
        "expected_discrepancies": [DiscrepancyType.TAX_MISMATCH],
        "max_reward": 1.00,
        "compliance_rule": "EU_VAT_DIRECTIVE_2006_112_EC",
    },
    "duplicate-invoice-detection": {
        "description": "Invoice INV-1001 already processed. Agent must reject duplicate per SOX 404.",
        "invoice": Invoice( 
            invoice_id="INV-1001", vendor_name="Acme Supplies Ltd.", invoice_date=date(2025, 3, 10),
            line_items=[LineItem(description="Office Chair", quantity=Decimal("10"),
                       unit_price=Decimal("150.00"), total=Decimal("1500.00"))],
            subtotal=Decimal("1500.00"), tax=Decimal("150.00"), total_amount=Decimal("1650.00"),
            currency="USD", po_reference="PO-5001",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-5001",
                vendor_name="Acme Supplies Ltd.",
                issue_date=date(2025, 3, 1),
                line_items=[
                    LineItem(description="Office Chair", quantity=Decimal("10"),
                             unit_price=Decimal("150.00"), total=Decimal("1500.00")),
                ],
                total_amount=Decimal("1500.00"),
                currency="USD",
                approved_by="manager@buyer.com",
            ),
        ],
        "correct_po_id": "PO-5001",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-1001",
            po_id="PO-5001",
            received_date=date(2025, 3, 5),
            items_received=[
                LineItem(description="Office Chair", quantity=Decimal("10"),
                         unit_price=Decimal("150.00"), total=Decimal("1500.00")),
            ],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "reject",
        "expected_discrepancies": [DiscrepancyType.DUPLICATE_INVOICE],
        "max_reward": 1.00,
        "compliance_rule": "SOX_SECTION_404",
        "processed_invoices": ["INV-1001"], # NEW: Track for duplicate check
    },
    "partial-delivery-po": {
        "description": "GRN shows 8/10 received but invoice bills 10. Agent must calculate partial payment.",
        "invoice": Invoice(
            invoice_id="INV-6002", vendor_name="Global Tech Solutions Inc.", invoice_date=date(2025, 4, 6),
            line_items=[LineItem(description="Laptop Model X", quantity=Decimal("10"),
                       unit_price=Decimal("1100.00"), total=Decimal("11000.00"))],
            subtotal=Decimal("11000.00"), tax=Decimal("1100.00"), total_amount=Decimal("12100.00"),
            currency="USD", po_reference="PO-5003",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-5003",
                vendor_name="Global Tech Solutions Inc.",
                issue_date=date(2025, 3, 10),
                line_items=[
                    LineItem(description="Laptop Model X", quantity=Decimal("10"),
                             unit_price=Decimal("1100.00"), total=Decimal("11000.00")),
                ],
                total_amount=Decimal("11000.00"),
                currency="USD",
                approved_by="it_director@buyer.com",
            )
        ],
        "correct_po_id": "PO-5003",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-6002", po_id="PO-5003", received_date=date(2025, 4, 4),
            items_received=[LineItem(description="Laptop Model X", quantity=Decimal("8"), # 8 not 10
                           unit_price=Decimal("1100.00"), total=Decimal("8800.00"))],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "flag_discrepancy",
        "expected_discrepancies": [DiscrepancyType.QUANTITY_MISMATCH],
        "max_reward": 1.20,
    },
    "vendor-sanctions-check": {
        "description": "Vendor on OFAC sanctions list. Must reject regardless of price/PO match per federal law.",
        "invoice": Invoice(
            invoice_id="INV-6003", vendor_name="BlockedCorp LLC", invoice_date=date(2025, 4, 7),
            line_items=[LineItem(description="Raw Materials", quantity=Decimal("100"),
                       unit_price=Decimal("50.00"), total=Decimal("5000.00"))],
            subtotal=Decimal("5000.00"), tax=Decimal("500.00"), total_amount=Decimal("5500.00"),
            currency="USD", po_reference="PO-8002",
        ),
        "available_pos": [
            PurchaseOrder(
                po_id="PO-8002", vendor_name="BlockedCorp LLC", issue_date=date(2025, 3, 30),
                line_items=[LineItem(description="Raw Materials", quantity=Decimal("100"),
                           unit_price=Decimal("50.00"), total=Decimal("5000.00"))],
                total_amount=Decimal("5000.00"), currency="USD", approved_by="procurement@buyer.com",
            ),
        ],
        "correct_po_id": "PO-8002",
        "goods_received_note": GoodsReceivedNote(
            grn_id="GRN-6003", po_id="PO-8002", received_date=date(2025, 4, 5),
            items_received=[LineItem(description="Raw Materials", quantity=Decimal("100"),
                           unit_price=Decimal("50.00"), total=Decimal("5000.00"))],
            received_by="warehouse@buyer.com",
        ),
        "expected_final_action": "reject",
        "expected_discrepancies": [DiscrepancyType.VENDOR_NAME_MISMATCH],
        "max_reward": 1.20,
        "compliance_rule": "OFAC_SANCTIONS_LIST",
        "sanctioned_vendors": ["BlockedCorp LLC"],
    },
}


# ---------------------------------------------------------------------------
# Internal episode state
# ---------------------------------------------------------------------------

# Task-level max_steps limits (must match openenv.yaml)
_MAX_STEPS: dict[str, int] = {
    "easy-exact-match":           8,
    "medium-fuzzy-match":        10,
    "hard-discrepancy-detection": 12,
    "ambiguous-split-invoice":    14,
    "compliance-soc2-vendor":     10,   # 2 items + compliance flag
    "multi-currency-compliance":  10,   # 2 items + FX flag
    "vat-reverse-charge":         10,
    "duplicate-invoice-detection": 10,
    "partial-delivery-po":        10,
    "vendor-sanctions-check":     10,
}


class _EpisodeState:
    """Holds mutable state for a single episode."""

    def __init__(self, episode_id: str, task_id: str, scenario: dict[str, Any]) -> None:
        self.episode_id = episode_id
        self.task_id = task_id
        self.scenario = scenario

        self.step: int = 0
        self.stage: str = "select_po"
        self.cumulative_reward: float = 0.0
        self.max_steps: int = _MAX_STEPS.get(task_id, 12)

        # ── Atomicity Tracking (Audit Fix #2) ────────────────────────────
        self.rewarded_compare_indices: set[int] = set()
        self.rewarded_discrepancy_types: set[str] = set()

        # Filled as the agent progresses
        self.selected_po: PurchaseOrder | None = None
        self.comparison_results: list[dict[str, Any]] = []
        self.flagged_discrepancies: list[Discrepancy] = []
        self.action_history: list[dict[str, Any]] = []   # for info/debugging

        # Pre-compute the ground-truth discrepancies for grading
        self._ground_truth_discrepancies: list[DiscrepancyType] = list(
            scenario["expected_discrepancies"]
        )

    # ── convenience properties ─────────────────────────────────────────────

    @property
    def invoice(self) -> Invoice:
        return self.scenario["invoice"]

    @property
    def available_pos(self) -> list[PurchaseOrder]:
        return self.scenario["available_pos"]

    @property
    def grn(self) -> GoodsReceivedNote | None:
        return self.scenario.get("goods_received_note")

    @property
    def correct_po_id(self) -> str:
        return self.scenario["correct_po_id"]

    @property
    def expected_final_action(self) -> str:
        return self.scenario["expected_final_action"]

    @property
    def expected_discrepancies(self) -> list[DiscrepancyType]:
        return self._ground_truth_discrepancies


# ---------------------------------------------------------------------------
# Helper: fuzzy word-overlap key matching
# ---------------------------------------------------------------------------

def _fuzzy_match_key(key: str, candidates: Any) -> str | None:
    key_words = set(key.split())
    best: str | None = None
    best_score = 0
    for candidate in candidates:
        score = len(key_words & set(candidate.split()))
        if score > best_score:
            best_score = score
            best = candidate
    return best if best_score > 0 else None


# ---------------------------------------------------------------------------
# Environment class
# ---------------------------------------------------------------------------

class InvoiceReconciliationEnv:
    """Stateful multi-step OpenEnv environment for Invoice Reconciliation.

    Episode lifecycle
    -----------------
    reset(task_id)  →  stage="select_po",       step=0
    step(SelectPOAction)  →  stage="compare_items",       step=1   reward≤+0.20
    step(CompareItemAction) × N  →  stage="flag_discrepancies", step=1+N  reward≤+0.10 each
    step(FlagDiscrepancyAction) × M  →  step=1+N+M            reward≤+0.10 each
    step(FinalDecisionAction)  →  stage="finished", done=True   reward≤+0.40
    """

    def __init__(self) -> None:
        self._ep: _EpisodeState | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, task_id: str) -> InvoiceObservation:
        """Initialise a new episode and return the first observation."""
        if task_id not in _SCENARIOS:
            raise ValueError(
                f"Unknown task_id '{task_id}'. Valid: {list(_SCENARIOS.keys())}"
            )
        scenario = _SCENARIOS[task_id]
        self._ep = _EpisodeState(
            episode_id=str(uuid.uuid4()),
            task_id=task_id,
            scenario=scenario,
        )
        return self._make_obs(
            reward=0.0,
            info={"description": scenario["description"]},
            feedback=(
                "Episode started. "
                f"Inspect the invoice and {len(scenario['available_pos'])} available PO(s). "
                "Submit a 'select_po' action to choose the best matching Purchase Order."
            ),
        )

    def step(self, action: InvoiceAction) -> InvoiceObservation:  # type: ignore[valid-type]
        """Advance the episode by one step."""
        ep = self._ep
        if ep is None:
            raise RuntimeError("Call reset() before step().")
        if ep.stage == "finished":
            raise RuntimeError("Episode is already finished. Call reset().")

        ep.step += 1

        # ── STAGE GATING (Audit Fix #1, #3 & #6) ──────────────────────────
        required_stage = {
            "SelectPOAction": "select_po",
            "CompareItemAction": "compare_items",
            "FlagDiscrepancyAction": "flag_discrepancies",
            "FinalDecisionAction": "flag_discrepancies",
        }.get(type(action).__name__)

        if ep.stage != required_stage:
            penalty = -0.10
            ep.cumulative_reward = round(ep.cumulative_reward + penalty, 4)
            return self._make_obs(
                reward=penalty,
                info={"error": f"Invalid stage '{ep.stage}' for action '{type(action).__name__}'"},
                feedback=f"Follow sequence: select_po -> compare_items -> flag_discrepancies -> final_decision."
            )

        # Record action in history
        ep.action_history.append(
            {"step": ep.step, "stage": ep.stage, "action_type": getattr(action, "action_type", "unknown")}
        )

        if isinstance(action, SelectPOAction):
            reward, info, feedback = self._handle_select_po(action, ep)
        elif isinstance(action, CompareItemAction):
            reward, info, feedback = self._handle_compare_item(action, ep)
        elif isinstance(action, FlagDiscrepancyAction):
            reward, info, feedback = self._handle_flag_discrepancy(action, ep)
        elif isinstance(action, FinalDecisionAction):
            reward, info, feedback = self._handle_final_decision(action, ep)
        else:
            reward = -0.05
            info = {"error": "Unknown action type.", "reward_breakdown": {"unknown_action": -0.05}}
            feedback = "Unknown action type. No stage change."

        # ── Max-steps enforcement ──────────────────────────────────────────
        if ep.step >= ep.max_steps and ep.stage != "finished":
            penalty = -0.10
            reward += penalty
            ep.stage = "finished"
            info["max_steps_reached"] = True
            info["incomplete_penalty"] = penalty
            info.setdefault("reward_breakdown", {})["incomplete_penalty"] = penalty
            feedback += f" ⚠ Max steps ({ep.max_steps}) reached — episode terminated early (−0.10)."

        ep.cumulative_reward += reward
        info["step"] = ep.step
        info["cumulative_reward"] = round(ep.cumulative_reward, 4)
        return self._make_obs(reward=reward, info=info, feedback=feedback)

    def state(self) -> InvoiceObservation:
        """Return the current observation without advancing the episode."""
        if self._ep is None:
            raise RuntimeError("Call reset() before state().")
        return self._make_obs(reward=0.0, info={}, feedback="")

    # ------------------------------------------------------------------
    # Stage handlers
    # ------------------------------------------------------------------

    def state(self) -> InvoiceObservation:
        """Return the current observation without advancing the episode. Mandatory for OpenEnv spec."""
        if not self._ep:
            raise RuntimeError("Call reset() before state().")
        # Return observation with 0.0 reward for the current 'peek' operation
        return self._make_obs(reward=0.0, info={}, feedback="Peeked at current state.")

    def _handle_select_po(
        self, action: SelectPOAction, ep: _EpisodeState
    ) -> tuple[float, dict[str, Any], str]:
        if ep.stage != "select_po":
            return (
                -0.05,
                {
                    "error": f"Expected stage 'select_po', current stage is '{ep.stage}'.",
                    "reward_breakdown": {"wrong_stage_penalty": -0.05},
                },
                f"Wrong action for stage '{ep.stage}'. Please submit a '{ep.stage}' action.",
            )

        # Check whether the chosen PO exists in candidates
        chosen_po = next((p for p in ep.available_pos if p.po_id == action.po_id), None)
        if chosen_po is None:
            return (
                0.0,
                {
                    "po_selection": "invalid",
                    "submitted_po_id": action.po_id,
                    "reward_breakdown": {"po_selection": 0.0},
                },
                f"PO '{action.po_id}' not found in available candidates. Try again.",
            )

        correct = action.po_id == ep.correct_po_id
        # Correct PO → +0.20 | Wrong (but valid) PO → −0.10 (stage still advances)
        reward = 0.20 if correct else -0.10
        ep.selected_po = chosen_po
        ep.stage = "compare_items"

        n_items = len(ep.invoice.line_items)
        info: dict[str, Any] = {
            "stage_reward":     reward,
            "po_selection":     "correct" if correct else "incorrect",
            "correct_po_id":    ep.correct_po_id,
            "submitted_po_id":  action.po_id,
            "reward_breakdown": {"po_selection": reward},
        }
        feedback = (
            f"PO '{action.po_id}' selected ({'correct ✓ (+0.20)' if correct else 'incorrect ✗ (−0.10)'})."
            f" Now compare each of the {n_items} invoice line item(s) against the selected PO "
            "and GRN using 'compare_item' actions (one per item, by 0-based index)."
        )
        return reward, info, feedback

    def _handle_compare_item(
        self, action: CompareItemAction, ep: _EpisodeState
    ) -> tuple[float, dict[str, Any], str]:
        if ep.stage != "compare_items":
            return (
                -0.05,
                {"error": f"Expected stage 'compare_items', current is '{ep.stage}'."},
                f"Wrong action for stage '{ep.stage}'.",
            )

        invoice = ep.invoice
        if action.invoice_item_index < 0 or action.invoice_item_index >= len(invoice.line_items):
            return (
                0.0,
                {"error": f"invoice_item_index {action.invoice_item_index} out of range."},
                f"Index {action.invoice_item_index} is out of range (0–{len(invoice.line_items)-1}).",
            )

        inv_item = invoice.line_items[action.invoice_item_index]
        po = ep.selected_po
        grn = ep.grn

        # --- Ground truth for this item ---
        po_items = (
            {" ".join(i.description.lower().split()): i for i in po.line_items}
            if po else {}
        )
        inv_key = " ".join(inv_item.description.lower().split())
        matched_po_key = _fuzzy_match_key(inv_key, po_items.keys())

        gt_found_in_po = matched_po_key is not None
        gt_price_matches = False
        gt_qty_matches = False

        if gt_found_in_po and matched_po_key:
            po_item = po_items[matched_po_key]
            gt_price_matches = inv_item.unit_price == po_item.unit_price

            if grn:
                grn_items = {" ".join(i.description.lower().split()): i for i in grn.items_received}
                matched_grn_key = _fuzzy_match_key(inv_key, grn_items.keys())
                if matched_grn_key:
                    grn_item = grn_items[matched_grn_key]
                    gt_qty_matches = inv_item.quantity == grn_item.quantity
        else:
            gt_qty_matches = False

        # --- Evaluate agent's claim ---
        found_correct    = action.found_in_po == gt_found_in_po
        price_correct    = action.price_matches == gt_price_matches
        qty_correct      = action.quantity_matches == gt_qty_matches
        all_correct      = found_correct and price_correct and qty_correct

        # ── ATOMIC REWARDS (Audit Fix #2) ────────────────────────────────
        reward = 0.0
        if action.invoice_item_index not in ep.rewarded_compare_indices:
            reward = 0.10 if all_correct else (0.04 if (found_correct or price_correct or qty_correct) else 0.0)
            if reward > 0:
                ep.rewarded_compare_indices.add(action.invoice_item_index)

        result_entry = {
            "invoice_item_index":    action.invoice_item_index,
            "invoice_description":   inv_item.description,
            "agent_found_in_po":     action.found_in_po,
            "agent_price_matches":   action.price_matches,
            "agent_qty_matches":     action.quantity_matches,
            "gt_found_in_po":        gt_found_in_po,
            "gt_price_matches":      gt_price_matches,
            "gt_qty_matches":        gt_qty_matches,
            "correct":               all_correct,
            "stage_reward":          reward,
        }
        ep.comparison_results.append(result_entry)

        # Determine if all items have been compared
        compared_indices = {r["invoice_item_index"] for r in ep.comparison_results}
        all_compared = compared_indices >= set(range(len(invoice.line_items)))
        if all_compared:
            ep.stage = "flag_discrepancies"

        info: dict[str, Any] = {
            "stage_reward":     reward,
            "item_result":      result_entry,
            "stage_advance":    all_compared,
            "reward_breakdown": {
                "found_in_po_correct":    found_correct,
                "price_correct":          price_correct,
                "quantity_correct":       qty_correct,
                "item_comparison_reward": reward,
            },
        }
        feedback = (
            f"Item #{action.invoice_item_index} ('{inv_item.description}') evaluated "
            f"({'all correct ✓' if all_correct else 'some incorrect ✗'}, {reward:+.2f}). "
        ) + (
            "All items compared — now submit 'flag_discrepancy' actions for each discrepancy found, "
            "then finish with a 'final_decision'."
            if all_compared else
            f"{len(invoice.line_items) - len(compared_indices)} item(s) remaining to compare."
        )
        return reward, info, feedback

    def _handle_flag_discrepancy(
        self, action: FlagDiscrepancyAction, ep: _EpisodeState
    ) -> tuple[float, dict[str, Any], str]:
        # Gating already handled by step() but we add safety
        if ep.stage != "flag_discrepancies":
             return -0.10, {"error": "Must complete all comparisons first."}, "Follow stage sequence."

        # Check if this discrepancy is real (in ground truth)
        correct = action.discrepancy_type in ep.expected_discrepancies

        # ── ATOMIC REWARDS (Audit Fix #2) ────────────────────────────────
        reward = 0.0
        if action.discrepancy_type.value not in ep.rewarded_discrepancy_types:
            reward = 0.10 if correct else -0.05
            if reward > 0:
                ep.rewarded_discrepancy_types.add(action.discrepancy_type.value)
        else:
            return 0.0, {"duplicate_flag": action.discrepancy_type.value}, "Already rewarded."

        discrepancy_obj = Discrepancy(
            discrepancy_type=action.discrepancy_type,
            field="agent_flagged",
            invoice_value="(agent-identified)",
            expected_value="(ground-truth)",
            description=action.details,
        )
        ep.flagged_discrepancies.append(discrepancy_obj)

        info: dict[str, Any] = {
            "stage_reward":       reward,
            "discrepancy_type":   action.discrepancy_type.value,
            "flag_correct":       correct,
            "total_flagged":      len(ep.flagged_discrepancies),
            "expected_remaining": [
                d.value for d in ep.expected_discrepancies
                if d not in {x.discrepancy_type for x in ep.flagged_discrepancies}
            ],
            "reward_breakdown": {
                "discrepancy_flag": reward,
                "reason": "valid" if correct else "spurious",
            },
        }
        feedback = (
            f"Flagged '{action.discrepancy_type.value}' "
            f"({'valid ✓' if correct else 'spurious ✗'}, {reward:+.2f}). "
            f"Flags so far: {[d.discrepancy_type.value for d in ep.flagged_discrepancies]}. "
            "When done flagging, submit a 'final_decision' action."
        )
        return reward, info, feedback

    def _handle_final_decision(
        self, action: FinalDecisionAction, ep: _EpisodeState
    ) -> tuple[float, dict[str, Any], str]:
        if ep.stage != "flag_discrepancies":
            return (
                -0.10,
                {"error": f"Cannot submit final_decision in stage '{ep.stage}'. Complete all compare_item and flag_discrepancy steps first."},
                f"Invalid stage. You must flag discrepancies before final decision."
            )

        ep.stage = "finished"

        # ── Decision reward: +0.30 correct, −0.30 wrong (partial credit style) ──
        action_correct = action.decision == ep.expected_final_action
        decision_reward = 0.30 if action_correct else -0.30

        # ── Constraint identification reward (0–0.20, prorated) ───────────
        expected_set  = set(ep.expected_discrepancies)
        submitted_set = set(action.discrepancy_flags)
        flagged_set   = {d.discrepancy_type for d in ep.flagged_discrepancies}
        # Union: credit flags from either stage 3 OR the final action's list
        final_flags = submitted_set | flagged_set

        if expected_set:
            correctly_covered = final_flags & expected_set
            disc_reward = 0.20 * (len(correctly_covered) / len(expected_set))
        else:
            # No discrepancies expected — full credit if agent flagged nothing
            disc_reward = 0.20 if not final_flags else 0.10

        total_step_reward = round(decision_reward + disc_reward, 4)
        final_cumulative  = round(ep.cumulative_reward + total_step_reward, 4)

        # ── Normalised score 0.0–1.0 ──────────────────────────────────────
        max_reward = float(ep.scenario.get("max_reward", 1.20))
        # ── Normalised score strictly within [0.01, 0.99] (Audit Fix #4 - Spec Compliance)
        raw_score = final_cumulative / max_reward
        normalized_score = round(max(0.01, min(0.99, raw_score)), 4)

        result_label = (
            "correct"   if action_correct and disc_reward >= 0.08 else
            "partial"   if action_correct or disc_reward > 0      else
            "incorrect"
        )

        # ── FLAT METADATA (Audit Fix #7) ──────────────────────────────────
        info: dict[str, Any] = {
            "normalized_score":        normalized_score,   # Top-level for scoring tools
            "cumulative_reward":        final_cumulative,
            "max_possible_reward":      max_reward,
            "is_correct":               action_correct,
            "result_label":             result_label,
            # Nested details...
            "stage_reward":           total_step_reward,
            "decision_correct":       action_correct,
            "expected_final_action":  ep.expected_final_action,
            "submitted_decision":     action.decision,
            "expected_discrepancies": [d.value for d in expected_set],
            "submitted_disc_flags":   [d.value for d in submitted_set],
            "stage3_flagged":         [d.value for d in flagged_set],
            "result":                 result_label,
            # ── Key scoring outputs ──────────────────────────────────────
            "normalized_score":        normalized_score,   # 0.0–1.0 for judge comparison
            "cumulative_reward":        final_cumulative,
            "max_possible_reward":      max_reward,
            "reward_breakdown": {
                "decision_reward":      decision_reward,
                "discrepancy_reward":   round(disc_reward, 4),
                "total_step_reward":    total_step_reward,
                "note": (
                    "correct decision (+0.30)" if action_correct
                    else f"WRONG decision (−0.60): expected '{ep.expected_final_action}'"
                ),
            },
        }
        decision_label = (
            "correct ✓ (+0.30)" if action_correct
            else f"WRONG ✗ (−0.60), expected '{ep.expected_final_action}'"
        )
        feedback = (
            f"Final decision '{action.decision}' ({decision_label})."
            f" Discrepancy coverage: {disc_reward:.2f}."
            f" Cumulative: {final_cumulative:.2f} / {max_reward:.2f}"
            f" → normalized_score = {normalized_score:.4f}."
        )
        return total_step_reward, info, feedback

    def get_action_mask(self) -> list[str]:
        """Proves action masking: returns allowed actions for current stage."""
        if not self._ep:
            return []
        return {
            "select_po": ["select_po"],
            "compare_items": ["compare_item"],
            "flag_discrepancies": ["flag_discrepancy", "final_decision"],
        }.get(self._ep.stage, [])

    # ------------------------------------------------------------------
    # Internal observation builder
    # ------------------------------------------------------------------

    def _make_obs(
        self,
        reward: float,
        info: dict[str, Any],
        feedback: str,
    ) -> InvoiceObservation:
        ep = self._ep
        assert ep is not None

        # ── Compute confidence scores ──────────────────────────────────────
        confidence: dict[str, float] = {}
        if ep.selected_po:
            confidence["po_selection"] = 1.0 if ep.selected_po.po_id == ep.correct_po_id else 0.3
        if ep.comparison_results:
            correct = sum(1 for r in ep.comparison_results if r.get("correct"))
            confidence["item_comparison"] = round(correct / len(ep.comparison_results), 2)
        needs_review = min(confidence.values(), default=1.0) < 0.8 if confidence else False
        compliance_rule = ep.scenario.get("compliance_rule")

        # ── Compute Action Mask ───────────────────────────────────────────
        allowed = {
            "select_po": ["select_po"],
            "compare_items": ["compare_item"],
            "flag_discrepancies": ["flag_discrepancy", "final_decision"],
        }.get(ep.stage, [])

        return InvoiceObservation(
            episode_id=ep.episode_id,
            task_id=ep.task_id,
            step=ep.step,
            invoice=ep.invoice,
            available_pos=ep.available_pos,
            goods_received_note=ep.grn,
            selected_po=ep.selected_po,
            comparison_results=ep.comparison_results,
            flagged_discrepancies=ep.flagged_discrepancies,
            stage=ep.stage,  # type: ignore[arg-type]
            is_done=(ep.stage == "finished"),
            reward=reward,
            cumulative_reward=ep.cumulative_reward,
            info=info,
            feedback=feedback,
            confidence=confidence,
            needs_review=needs_review,
            compliance_check=compliance_rule,
            action_history=ep.action_history,
            allowed_action_types=allowed,
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

env = InvoiceReconciliationEnv()
