import pytest
from server.env import InvoiceReconciliationEnv
from server.models import SelectPOAction, CompareItemAction, FinalDecisionAction

def test_random_agent_fails():
    """Exploit bot check: random actions or skipping stages should fail"""
    env = InvoiceReconciliationEnv()
    scores = []
    for _ in range(5):
        obs = env.reset("hard-discrepancy-detection")
        # Attempt Final Decision immediately (Exploit Bot strategy)
        # Note: action_type="final_decision" is default in FinalDecisionAction
        action = FinalDecisionAction(decision="approve")
        obs = env.step(action)
        scores.append(obs.cumulative_reward)
    
    avg_score = sum(scores)/len(scores)
    # Each should have return -0.10 penalty for wrong stage
    assert avg_score < 0, f"Exploit defense failed! Avg score: {avg_score}"

def test_greedy_agent_fails():
    """Greedy 'always approve' should fail on discrepancy tasks"""
    env = InvoiceReconciliationEnv()
    obs = env.reset("hard-discrepancy-detection") 
    
    # Must follow stage progression: select_po
    obs = env.step(SelectPOAction(po_id="PO-5003")) # Correct PO
    
    # Must follow stage progression: compare_items
    for i in range(len(obs.invoice.line_items)):
        item = obs.invoice.line_items[i]
        obs = env.step(CompareItemAction(
            invoice_item_index=i, 
            po_item_description=item.description, # matching description
            found_in_po=True, 
            price_matches=True, 
            quantity_matches=True
        ))
    
    # Now in flag_discrepancies stage.
    # Greedy: Skip flagging, go straight to final_decision
    obs = env.step(FinalDecisionAction(
        decision="approve", 
        matched_po_id="PO-5003", 
        discrepancy_flags=[]
    ))
    
    # Since it's a 'reject' task (sanctions or discrepancy), 'approve' should return -0.30
    # Final cumulative should be around +0.2 (po) + 0.1 (item) - 0.3 (decision) = 0.0
    assert obs.cumulative_reward < 0.6, f"Greedy approve should fail on reject task. Score: {obs.cumulative_reward}"
