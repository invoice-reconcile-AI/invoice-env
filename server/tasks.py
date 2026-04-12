from typing import Any
from datetime import date
from decimal import Decimal
from server.models import Invoice, LineItem, PurchaseOrder, CompareItemAction, DiscrepancyType, GoodsReceivedNote, Discrepancy

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


    "medium-fuzzy-match-var-1": {
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

    "hard-discrepancy-detection-var-2": {
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
    "ambiguous-split-invoice-var-3": {
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
    "compliance-soc2-vendor-var-4": {
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
    "multi-currency-compliance-var-5": {
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

    "vat-reverse-charge-var-6": {
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
    "duplicate-invoice-detection-var-7": {
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
    "partial-delivery-po-var-8": {
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
    "vendor-sanctions-check-var-9": {
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
    "easy-exact-match-var-10": {
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

    "medium-fuzzy-match-var-11": {
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

    "hard-discrepancy-detection-var-12": {
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
    "ambiguous-split-invoice-var-13": {
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
    "compliance-soc2-vendor-var-14": {
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
    "multi-currency-compliance-var-15": {
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

    "vat-reverse-charge-var-16": {
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
    "duplicate-invoice-detection-var-17": {
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
    "partial-delivery-po-var-18": {
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
    "vendor-sanctions-check-var-19": {
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
    "easy-exact-match-var-20": {
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

    "medium-fuzzy-match-var-21": {
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

    "hard-discrepancy-detection-var-22": {
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
    "ambiguous-split-invoice-var-23": {
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
    "compliance-soc2-vendor-var-24": {
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
    "multi-currency-compliance-var-25": {
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

    "vat-reverse-charge-var-26": {
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
    "duplicate-invoice-detection-var-27": {
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
    "partial-delivery-po-var-28": {
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
    "vendor-sanctions-check-var-29": {
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
    "easy-exact-match-var-30": {
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

    "medium-fuzzy-match-var-31": {
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

    "hard-discrepancy-detection-var-32": {
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
    "ambiguous-split-invoice-var-33": {
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
    "compliance-soc2-vendor-var-34": {
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
    "multi-currency-compliance-var-35": {
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

    "vat-reverse-charge-var-36": {
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
    "duplicate-invoice-detection-var-37": {
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
    "partial-delivery-po-var-38": {
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
    "vendor-sanctions-check-var-39": {
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
    "easy-exact-match-var-40": {
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

    "medium-fuzzy-match-var-41": {
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

    "hard-discrepancy-detection-var-42": {
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
    "ambiguous-split-invoice-var-43": {
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
    "compliance-soc2-vendor-var-44": {
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
}
