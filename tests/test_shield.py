import pytest
from server.env import InvoiceReconciliationEnv
from server.models import SelectPOAction, CompareItemAction, FlagDiscrepancyAction, FinalDecisionAction, DiscrepancyType

def test_exploit_shortcut_denied():
    """Vulnerability #1 & #3: Ensure final_decision cannot be called before Stage 3 starts."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    
    # Attempt final_decision on Turn 1
    obs = env.step(FinalDecisionAction(decision="approve", matched_po_id="PO-123", reasoning="..."))
    
    assert obs.reward == -0.10
    assert "Invalid stage" in obs.info["error"]
    assert obs.stage == "select_po" # Stage must not advance

def test_reward_farming_denied():
    """Vulnerability #2: Ensure repeated correct actions don't grant multiple rewards."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    
    # Turn 1: Valid Select PO
    obs1 = env.step(SelectPOAction(po_id="PO-5001"))
    first_reward = obs1.reward
    
    # Turn 2: Repeat Select PO (Should be rejected by stage gating now)
    obs2 = env.step(SelectPOAction(po_id="PO-5001"))
    assert obs2.reward == -0.10 # Rejected because stage is now compare_items
    
    # Turn 3: Valid Compare Item
    obs3 = env.step(CompareItemAction(
        invoice_item_index=0, 
        po_item_description="...", 
        found_in_po=True, 
        price_matches=True, 
        quantity_matches=True
    ))
    reward_a = obs3.reward
    assert reward_a > 0
    
    # Turn 4: Repeat Identical Compare Item (Farming attempt)
    obs4 = env.step(CompareItemAction(
        invoice_item_index=0, 
        po_item_description="...", 
        found_in_po=True, 
        price_matches=True, 
        quantity_matches=True
    ))
    assert obs4.reward == 0.0 # No reward for duplicate index
    
def test_discrepancy_farming_denied():
    """Vulnerability #2: Ensure repeated discrepancy flags don't grant multiple rewards."""
    env = InvoiceReconciliationEnv()
    env.reset("hard-discrepancy-detection")
    
    # Advance to Stage 3
    env.step(SelectPOAction(po_id="PO-5003"))
    for i in range(3): # Hard task has 3 items
        env.step(CompareItemAction(invoice_item_index=i, po_item_description="...", found_in_po=True, price_matches=True, quantity_matches=True))
        
    # Turn 1: Valid Flag
    obs1 = env.step(FlagDiscrepancyAction(discrepancy_type=DiscrepancyType.PRICE_MISMATCH, details="..."))
    reward1 = obs1.reward
    assert reward1 > 0
    
    # Turn 2: Repeat Same Flag
    obs2 = env.step(FlagDiscrepancyAction(discrepancy_type=DiscrepancyType.PRICE_MISMATCH, details="..."))
    assert obs2.reward == 0.0 # No reward for duplicate flag
    assert "Already rewarded" in obs2.feedback

def test_perfect_score_trust():
    """Vulnerability #4: Ensure 100% correct tasks can reach 1.0 (Judge Trust)."""
    env = InvoiceReconciliationEnv()
    # Use a task where we can easily get max reward
    env.reset("easy-exact-match")
    
    env.step(SelectPOAction(po_id="PO-5001"))
    # easy-exact-match has 2 items
    for i in range(2):
        env.step(CompareItemAction(
            invoice_item_index=i, 
            po_item_description="...", 
            found_in_po=True, 
            price_matches=True, 
            quantity_matches=True
        ))
    obs = env.step(FinalDecisionAction(decision="approve", matched_po_id="PO-5001", reasoning="..."))
    # Verify 0.99 cap for spec compliance
    assert obs.info["normalized_score"] == 0.99 
