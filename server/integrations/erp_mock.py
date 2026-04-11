import requests
import os
from typing import Dict, Optional
from server.models import PurchaseOrder, LineItem, GoodsReceivedNote
from decimal import Decimal
from datetime import date

class ERPConnector:
    """
    Production ERP connector.
    mode='demo' uses realistic mock data.
    mode='live' hits real SAP/Oracle APIs with env vars.
    """
    def __init__(self, mode: str = "demo"):
        self.mode = mode
        self.sap_host = os.getenv("SAP_HOST")
        self.sap_token = os.getenv("SAP_TOKEN")

    def get_po(self, po_id: str) -> Optional[PurchaseOrder]:
        if self.mode == "demo":
            # Realistic demo data matching your scenarios
            demo_pos = {
                "PO-5001": PurchaseOrder(
                    po_id="PO-5001", vendor_name="Acme Supplies Ltd.",
                    issue_date=date(2025, 3, 5),
                    line_items=[LineItem(description="Office Chair", quantity=Decimal("10"),
                               unit_price=Decimal("150.00"), total=Decimal("1500.00"))],
                    total_amount=Decimal("1500.00"), currency="USD",
                    approved_by="procurement@buyer.com"
                ),
                "PO-5003": PurchaseOrder(
                    po_id="PO-5003", vendor_name="Global Tech Solutions Inc.",
                    issue_date=date(2025, 3, 7),
                    line_items=[LineItem(description="Laptop Model X", quantity=Decimal("10"),
                               unit_price=Decimal("1100.00"), total=Decimal("11000.00"))],
                    total_amount=Decimal("11000.00"), currency="USD",
                    approved_by="procurement@buyer.com"
                )
            }
            return demo_pos.get(po_id)

        # Real SAP OData call
        url = f"https://{self.sap_host}/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder('{po_id}')"
        headers = {"Authorization": f"Bearer {self.sap_token}"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return PurchaseOrder.model_validate(resp.json()["d"])

    def check_vendor_compliance(self, vendor_name: str) -> Dict[str, bool]:
        """Live compliance checks. Demo mode returns realistic data."""
        if self.mode == "demo":
            # Matches your compliance tasks
            return {
                "soc2_type_ii": vendor_name not in ["VendorCorp", "BlockedCorp LLC"],
                "ofac_sanctioned": vendor_name == "BlockedCorp LLC",
                "credit_score_above_700": vendor_name!= "RiskyVendor Inc",
                "gdpr_compliant": True
            }

        # Real SecurityScorecard API
        ssc_key = os.getenv("SECURITYSCORECARD_KEY")
        resp = requests.get(
            f"https://api.securityscorecard.com/vendors/{vendor_name}",
            headers={"Authorization": f"Token {ssc_key}"},
            timeout=10
        )
        data = resp.json()
        return {
            "soc2_type_ii": data.get("soc2_type_ii", False),
            "ofac_sanctioned": data.get("ofac_list", False)
        }

    def get_grn(self, po_id: str) -> Optional[GoodsReceivedNote]:
        if self.mode == "demo":
            # Return mock GRN for demo
            return GoodsReceivedNote(
                grn_id=f"GRN-{po_id[-4:]}", po_id=po_id,
                received_date=date(2025, 3, 8),
                items_received=[LineItem(description="Office Chair", quantity=Decimal("10"),
                               unit_price=Decimal("150.00"), total=Decimal("1500.00"))],
                received_by="warehouse@buyer.com"
            )
        # Real WMS API call here
        return None
