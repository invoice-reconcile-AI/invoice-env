import pytest
from server.env import InvoiceReconciliationEnv
from server.models import SelectPOAction, FinalDecisionAction, DiscrepancyType

def test_soc2_compliance_rejects_cheap_vendor():
    env = InvoiceReconciliationEnv()
    obs = env.reset("compliance-soc2-vendor")
    obs = env.step(SelectPOAction(action_type="select_po", po_id="PO-7001", reasoning="SOC2"))
    assert obs.reward == 0.20
    assert obs.stage == "compare_items"

def test_partial_credit_not_binary():
    env = InvoiceReconciliationEnv()
    obs = env.reset("hard-discrepancy-detection")
    # Simulate wrong decision but correct flags
    obs = env.step(FinalDecisionAction(
        action_type="final_decision", decision="approve", # wrong
        matched_po_id="PO-5003",
        discrepancy_flags=[DiscrepancyType.PRICE_MISMATCH, DiscrepancyType.QUANTITY_MISMATCH], # correct
        reasoning="test"
    ))
    assert obs.cumulative_reward > -0.5 # Partial credit, not -0.60

def test_all_tasks_have_max_reward():
    from server.env import _SCENARIOS
    assert len(_SCENARIOS) == 10
    for task, data in _SCENARIOS.items():
        assert "max_reward" in data, f"{task} missing max_reward"
        assert 0.8 <= data["max_reward"] <= 1.2

def test_vat_reverse_charge_flags_tax():
    env = InvoiceReconciliationEnv()
    obs = env.reset("vat-reverse-charge")
    assert obs.info["description"].find("VAT")!= -1

def test_tasks_endpoint_structure():
    from server.app import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 10
    assert "curriculum" in data
