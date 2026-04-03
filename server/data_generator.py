# server/data_generator.py
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Literal, Optional
from faker import Faker

from server.models import PurchaseOrder, GoodsReceivedNote, Invoice # Import our Pydantic models

fake = Faker()

class InvoiceDataGenerator:
    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)
        self.products = [
            "Widget A", "Gadget B", "Doodad C", "Thingamajig D", "Sprocket E",
            "Gear F", "Lever G", "Pulley H", "Valve I", "Tube J"
        ]
        self.vendors = [
            "Acme Corp", "Globex Inc", "Soylent Corp", "Cyberdyne Systems",
            "Umbrella Corp", "Wayne Enterprises", "Stark Industries",
            "Horizon Corp", "Quantum Solutions", "Pinnacle Group"
        ]
        self.currencies = ["USD", "EUR", "GBP"]
        self.base_item_price = 10.0

    def _generate_item_quantities(self, num_items: int = None) -> Dict[str, int]:
        """Generates a dictionary of random item quantities."""
        if num_items is None:
            num_items = random.randint(1, 3)
        selected_products = random.sample(self.products, num_items)
        return {prod: random.randint(1, 20) for prod in selected_products}

    def _calculate_total_amount(self, items: Dict[str, int]) -> float:
        """Calculates total amount based on items and a base price."""
        total = sum(qty * self.base_item_price for qty in items.values())
        return round(total, 2)

    def generate_task_data(
        self, task_type: Literal["easy", "medium", "hard"]
    ) -> Tuple[Invoice, List[PurchaseOrder], List[GoodsReceivedNote], str, str, Dict[str, Any]]:
        """
        Generates a complete set of data for a single invoice reconciliation task.
        Returns: (invoice, candidate_pos, grn_log, true_po_id, correct_decision, discrepancy_details)
        """
        true_po = self._generate_matching_purchase_order()
        true_grn = self._generate_matching_goods_received_note(true_po)
        true_invoice = self._generate_matching_invoice(true_po)

        correct_decision = "pay"
        discrepancy_details = {}

        if task_type == "easy":
            true_invoice.extracted_po_ref = true_po.po_id
            true_invoice.raw_text_content = self._generate_raw_invoice_text(
                true_po, true_invoice.items_billed, true_invoice.total_amount, po_ref_in_text=true_po.po_id
            )
            correct_decision = "pay"
        elif task_type == "medium":
            true_invoice, discrepancy_details = self._inject_medium_discrepancies(true_invoice, true_po)
            correct_decision = "hold" if discrepancy_details else "pay"
            true_invoice.extracted_po_ref = None
        elif task_type == "hard":
            true_invoice, discrepancy_details = self._inject_hard_discrepancies(true_invoice, true_po, true_grn)
            correct_decision = "flag" if discrepancy_details else "pay"
            true_invoice.extracted_po_ref = None

        candidate_pos = self._generate_candidate_pos(true_po)
        grn_log = self._generate_grn_log(true_grn)

        true_invoice.discrepancy_details = discrepancy_details

        return true_invoice, candidate_pos, grn_log, true_po.po_id, correct_decision, discrepancy_details

    def _generate_matching_purchase_order(self) -> PurchaseOrder:
        """Generates a PurchaseOrder with reasonable, consistent data."""
        items = self._generate_item_quantities()
        total = self._calculate_total_amount(items)
        vendor = random.choice(self.vendors)
        issue_date_obj = fake.date_between(start_date='-60d', end_date='-30d')
        issue_date = issue_date_obj.strftime('%Y-%m-%d')
        
        line_items = []
        for name, qty in items.items():
            from server.models import LineItem
            line_items.append(LineItem(
                description=name,
                quantity=qty,
                unit_price=self.base_item_price,
                total=qty * self.base_item_price
            ))

        return PurchaseOrder(
            po_id=f"PO-{fake.unique.random_int(min=1000, max=9999)}",
            vendor_name=vendor,
            issue_date=issue_date_obj,
            line_items=line_items,
            total_amount=total,
            currency="USD",
            items_ordered=items,
            status="open",
            payment_terms="Net 30",
            approved_by="procurement@buyer.com"
        )

    def _generate_matching_goods_received_note(self, po: PurchaseOrder) -> GoodsReceivedNote:
        """Generates a GoodsReceivedNote matching a given PO."""
        po_date = po.issue_date
        received_date_obj = fake.date_between(
            start_date=po_date + timedelta(days=5),
            end_date=datetime.now().date() - timedelta(days=10)
        )

        return GoodsReceivedNote(
            grn_id=f"GRN-{fake.unique.random_int(min=1000, max=9999)}",
            po_id=po.po_id,
            received_date=received_date_obj,
            items_received=po.line_items.copy(),
            received_by=fake.name()
        )

    def _generate_matching_invoice(self, po: PurchaseOrder) -> Invoice:
        """Generates an Invoice matching a given PO."""
        po_date = po.issue_date
        invoice_date_obj = fake.date_between(
            start_date=po_date + timedelta(days=10),
            end_date=datetime.now().date() - timedelta(days=5)
        )
        invoice_date = invoice_date_obj.strftime('%Y-%m-%d')
        due_date = (invoice_date_obj + timedelta(days=30)).strftime('%Y-%m-%d')

        raw_text_content = self._generate_raw_invoice_text(po, po.items_ordered, po.total_amount, po_ref_in_text=None)

        return Invoice(
            invoice_id=f"INV-{fake.unique.random_int(min=1000, max=9999)}",
            vendor_name=po.vendor_name,
            invoice_date=invoice_date,
            due_date=due_date,
            total_amount=float(po.total_amount),
            subtotal=float(po.total_amount),
            tax=0.00,
            currency=po.currency,
            line_items=po.line_items.copy(),
            items_billed=po.items_ordered.copy(),
            raw_text_content=raw_text_content,
            extracted_po_ref=po.po_id,
            discrepancy_details={}
        )

    def _generate_raw_invoice_text(
        self,
        po: PurchaseOrder,
        items_for_text: Dict[str, int],
        total_amount_for_text: float,
        invoice_date_str: Optional[str] = None,
        vendor_name_in_text: Optional[str] = None,
        po_ref_in_text: Optional[str] = None
    ) -> str:
        """Generates a block of text simulating an invoice document."""
        current_invoice_date = invoice_date_str if invoice_date_str else fake.date_between(start_date='-30d', end_date='today').strftime('%Y-%m-%d')
        current_vendor_name = vendor_name_in_text if vendor_name_in_text else po.vendor_name
        due_date_str = (datetime.strptime(current_invoice_date, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')

        invoice_text_lines = [
            f"INVOICE {fake.unique.random_int(min=100000, max=999999)}",
            f"Date: {current_invoice_date}",
            f"Vendor: {current_vendor_name}",
            "---------------------------------------",
            "Description Qty Unit Price Amount",
        ]
        for item, qty in items_for_text.items():
            unit_price = self.base_item_price
            line_total = round(qty * unit_price, 2)
            invoice_text_lines.append(f"{item:<20} {qty:<5} {unit_price:<10.2f} {line_total:<10.2f}")

        invoice_text_lines.extend([
            "---------------------------------------",
            f"Total Amount: {po.currency} {total_amount_for_text:.2f}",
            f"Payment Terms: {po.payment_terms}",
            f"Due Date: {due_date_str}"
        ])

        if po_ref_in_text:
            invoice_text_lines.append(f"Purchase Order Ref: {po_ref_in_text}")
        elif po_ref_in_text is None:
            if random.random() < 0.7:
                 insert_line = random.randint(4, len(invoice_text_lines) - 2)
                 po_ref_phrasing = random.choice([
                     f"Order Reference: {po.po_id}",
                     f"Customer PO #: {po.po_id}",
                     f"Our Ref: {po.po_id}"
                 ])
                 invoice_text_lines.insert(insert_line, po_ref_phrasing)

        return "\n".join(invoice_text_lines)

    def _generate_candidate_pos(self, true_po: PurchaseOrder) -> List[PurchaseOrder]:
        """Generates a list of candidate POs, including the true PO and some distractors."""
        candidates = [true_po]
        num_distractors = random.randint(1, 2)
        for _ in range(num_distractors):
            distractor_po = self._generate_matching_purchase_order()
            distractor_po.po_id = f"PO-{fake.unique.random_int(min=20000, max=29999)}"
            if random.random() < 0.3:
                distractor_po.vendor_name = true_po.vendor_name
            candidates.append(distractor_po)
        random.shuffle(candidates)
        return candidates

    def _generate_grn_log(self, true_grn: GoodsReceivedNote) -> List[GoodsReceivedNote]:
        """Generates a log of GRNs, including the true GRN and possibly some unrelated ones."""
        log = [true_grn]
        for _ in range(random.randint(0, 2)):
            older_po = self._generate_matching_purchase_order()
            older_po.po_id = f"PO-{fake.unique.random_int(min=30000, max=39999)}"
            older_po.issue_date = fake.date_between(start_date='-180d', end_date='-90d')
            log.append(self._generate_matching_goods_received_note(older_po))
        random.shuffle(log)
        return log

    def _inject_medium_discrepancies(self, invoice: Invoice, po: PurchaseOrder) -> Tuple[Invoice, Dict[str, Any]]:
        discrepancy_details = {}

        invoice.extracted_po_ref = None

        if random.random() < 0.6:
            diff = round(random.uniform(0.01, 5.00), 2) * random.choice([-1, 1])
            invoice.total_amount = round(float(po.total_amount) + diff, 2)
            discrepancy_details["amount_diff"] = diff
            discrepancy_details["reason_amount_diff"] = "Minor rounding or small fee difference."

        if random.random() < 0.5:
            date_diff_days = random.randint(1, 3) * random.choice([-1, 1])
            original_invoice_date = datetime.strptime(invoice.invoice_date, '%Y-%m-%d')
            new_invoice_date_obj = original_invoice_date + timedelta(days=date_diff_days)
            invoice.invoice_date = new_invoice_date_obj.strftime('%Y-%m-%d')
            invoice.due_date = (new_invoice_date_obj + timedelta(days=30)).strftime('%Y-%m-%d')
            discrepancy_details["invoice_date_diff_days"] = date_diff_days
            discrepancy_details["reason_date_diff"] = f"Invoice date differs by {date_diff_days} days from expected."

        if random.random() < 0.4:
            original_vendor_name = po.vendor_name
            if "Corp" in original_vendor_name:
                variations = [original_vendor_name.replace("Corp", "Corporation"), original_vendor_name.replace("Corp", "Co.")]
            elif "Inc" in original_vendor_name:
                variations = [original_vendor_name.replace("Inc", "Incorporated"), original_vendor_name.replace("Inc", "Inc.")]
            else:
                variations = [f"{original_vendor_name} Ltd.", f"{original_vendor_name} Co."]

            if variations:
                new_vendor_name = random.choice(variations)
                invoice.vendor_name = new_vendor_name
                discrepancy_details["vendor_name_variation"] = {
                    "expected": original_vendor_name,
                    "actual": new_vendor_name
                }
                discrepancy_details["reason_vendor_name_variation"] = "Minor vendor name difference."
            else:
                new_vendor_name = original_vendor_name
        else:
            new_vendor_name = po.vendor_name

        invoice.raw_text_content = self._generate_raw_invoice_text(
            po,
            invoice.items_billed,
            invoice.total_amount,
            invoice_date_str=invoice.invoice_date,
            vendor_name_in_text=new_vendor_name,
            po_ref_in_text=None
        )

        return invoice, discrepancy_details

    def _inject_hard_discrepancies(self, invoice: Invoice, po: PurchaseOrder, grn: GoodsReceivedNote) -> Tuple[Invoice, Dict[str, Any]]:
        discrepancy_details = {}

        invoice.extracted_po_ref = None # Always force agent to read raw_text_content

        # Choose a type of hard discrepancy to inject (could be multiple with lower probabilities)
        discrepancy_type = random.choice([
            "quantity_mismatch",
            "item_mismatch",
            "incorrect_vendor",
            "major_price_mismatch"
        ])

        if discrepancy_type == "quantity_mismatch":
            # 1. Significant Quantity Mismatch (Invoice vs. PO/GRN)
            item_to_change = random.choice(list(po.items_ordered.keys()))
            po_qty = po.items_ordered[item_to_change]

            # Make the billed quantity significantly different
            if random.random() < 0.5: # Bill more
                new_invoice_qty = po_qty + random.randint(min(5, po_qty), max(10, po_qty + 5)) # Substantial increase
            else: # Bill less
                new_invoice_qty = max(1, po_qty - random.randint(min(5, po_qty), max(10, po_qty + 5))) # Substantial decrease, min 1

            invoice.items_billed[item_to_change] = new_invoice_qty
            invoice.total_amount = float(self._calculate_total_amount(invoice.items_billed)) # Recalculate total
            discrepancy_details["quantity_mismatch"] = {
                item_to_change: {"po_qty": po_qty, "invoice_qty": new_invoice_qty}
            }
            discrepancy_details["reason_quantity_mismatch"] = "Invoice quantity significantly differs from Purchase Order/GRN."

        elif discrepancy_type == "item_mismatch":
            # 2. Item Mismatch / Missing Item
            if random.random() < 0.5: # Scenario A: Invoice includes item not on PO/GRN
                new_item = random.choice([p for p in self.products if p not in po.items_ordered])
                invoice.items_billed[new_item] = random.randint(1, 10)
                discrepancy_details["item_added_to_invoice"] = {new_item: invoice.items_billed[new_item]}
                discrepancy_details["reason_item_mismatch"] = "Invoice includes an item not on the Purchase Order."
            else: # Scenario B: Invoice misses an item from PO/GRN
                item_to_remove = random.choice(list(invoice.items_billed.keys()))
                removed_qty = invoice.items_billed.pop(item_to_remove)
                discrepancy_details["item_removed_from_invoice"] = {item_to_remove: removed_qty}
                discrepancy_details["reason_item_mismatch"] = "Invoice is missing an item from the Purchase Order."

            invoice.total_amount = float(self._calculate_total_amount(invoice.items_billed)) # Recalculate total

        elif discrepancy_type == "incorrect_vendor":
            # 3. Completely Incorrect Vendor Name
            original_vendor = po.vendor_name
            other_vendors = [v for v in self.vendors if v!= original_vendor]
            if other_vendors:
                invoice.vendor_name = random.choice(other_vendors)
                discrepancy_details["incorrect_vendor"] = {"expected": original_vendor, "actual": invoice.vendor_name}
                discrepancy_details["reason_incorrect_vendor"] = "Invoice vendor does not match Purchase Order vendor."
            else: # Fallback if only one vendor is configured
                pass # No discrepancy injected if no other vendors available

        elif discrepancy_type == "major_price_mismatch":
            # 4. Major Price Mismatch (Total Amount)
            # Create a significant percentage difference, e.g., 20% to 50%
            price_factor = random.uniform(1.2, 1.5) if random.random() < 0.5 else random.uniform(0.5, 0.8)
            new_total = round(float(po.total_amount) * price_factor, 2)
            invoice.total_amount = new_total
            discrepancy_details["major_price_mismatch"] = {
                "po_total": float(po.total_amount),
                "invoice_total": new_total,
                "percentage_diff": round(((new_total - float(po.total_amount)) / float(po.total_amount)) * 100, 2)
            }
            discrepancy_details["reason_major_price_mismatch"] = "Invoice total amount significantly differs from Purchase Order."

        # After all changes, regenerate raw_text_content to reflect discrepancies
        invoice.raw_text_content = self._generate_raw_invoice_text(
            po,
            invoice.items_billed, # Use potentially modified items_billed
            invoice.total_amount, # Use potentially modified total_amount
            invoice_date_str=invoice.invoice_date,
            vendor_name_in_text=invoice.vendor_name, # Use potentially modified vendor name
            po_ref_in_text=None # Keep PO hidden for hard tasks
        )

        return invoice, discrepancy_details

if __name__ == "__main__":
    generator = InvoiceDataGenerator(seed=42)

    print("--- Easy Task ---")
    invoice_e, pos_e, grns_e, true_po_e, correct_decision_e, disc_e = generator.generate_task_data("easy")
    print(f"Invoice ID: {invoice_e.invoice_id}, True PO: {true_po_e}, Correct Decision: {correct_decision_e}")
    print(f"Discrepancies: {disc_e}")
    print(f"Vendor: {invoice_e.vendor_name}, Total: {invoice_e.total_amount}")
    print(invoice_e.raw_text_content)
    print("\n")

    print("--- Medium Task ---")
    invoice_m, pos_m, grns_m, true_po_m, correct_decision_m, disc_m = generator.generate_task_data("medium")
    print(f"Invoice ID: {invoice_m.invoice_id}, True PO: {true_po_m}, Correct Decision: {correct_decision_m}")
    print(f"Discrepancies: {disc_m}")
    print(f"Vendor: {invoice_m.vendor_name}, Total: {invoice_m.total_amount}")
    print(invoice_m.raw_text_content)
    print("\n")

    print("--- Hard Task ---")
    invoice_h, pos_h, grns_h, true_po_h, correct_decision_h, disc_h = generator.generate_task_data("hard")
    print(f"Invoice ID: {invoice_h.invoice_id}, True PO: {true_po_h}, Correct Decision: {correct_decision_h}")
    print(f"Discrepancies: {disc_h}")
    print(f"Vendor: {invoice_h.vendor_name}, Total: {invoice_h.total_amount}")
    print(invoice_h.raw_text_content)
    print("\n")
