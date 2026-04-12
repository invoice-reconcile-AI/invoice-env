"""Comprehensive tests covering previously untested paths in InvoiceReconciliationEnv."""

import pytest
from server.env import InvoiceReconciliationEnv, _fuzzy_match_key
from server.models import (
    CompareItemAction,
    DiscrepancyType,
    FinalDecisionAction,
    FlagDiscrepancyAction,
    SelectPOAction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _advance_to_flag_discrepancies(env: InvoiceReconciliationEnv, task_id: str, po_id: str, n_items: int) -> None:
    """Reset env and advance through select_po and compare_items stages."""
    env.reset(task_id)
    env.step(SelectPOAction(po_id=po_id))
    for i in range(n_items):
        env.step(CompareItemAction(
            invoice_item_index=i,
            po_item_description="...",
            found_in_po=True,
            price_matches=True,
            quantity_matches=True,
        ))


def _full_run(task_id, po_id, n_items, discrepancies, decision):
    """Run a full episode, flagging discrepancies in stage 3, then issuing a final decision."""
    env = InvoiceReconciliationEnv()
    env.reset(task_id)
    env.step(SelectPOAction(po_id=po_id))
    for i in range(n_items):
        env.step(CompareItemAction(
            invoice_item_index=i,
            po_item_description="...",
            found_in_po=True,
            price_matches=True,
            quantity_matches=True,
        ))
    for disc in discrepancies:
        env.step(FlagDiscrepancyAction(discrepancy_type=disc, details="test"))
    return env.step(FinalDecisionAction(
        decision=decision,
        matched_po_id=po_id,
        discrepancy_flags=discrepancies,
    ))


# ---------------------------------------------------------------------------
# Error / Guard tests
# ---------------------------------------------------------------------------


def test_reset_invalid_task_raises():
    env = InvoiceReconciliationEnv()
    with pytest.raises(ValueError, match="Unknown task_id"):
        env.reset("nonexistent-task")


def test_step_before_reset_raises():
    env = InvoiceReconciliationEnv()
    with pytest.raises(RuntimeError, match="Call reset\\(\\) before step\\(\\)"):
        env.step(SelectPOAction(po_id="PO-5001"))


def test_state_before_reset_raises():
    env = InvoiceReconciliationEnv()
    with pytest.raises(RuntimeError, match="Call reset\\(\\) before state\\(\\)"):
        env.state()


def test_step_after_done_raises():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    env.step(SelectPOAction(po_id="PO-5001"))
    for i in range(2):
        env.step(CompareItemAction(
            invoice_item_index=i, po_item_description="...",
            found_in_po=True, price_matches=True, quantity_matches=True,
        ))
    env.step(FinalDecisionAction(decision="approve", matched_po_id="PO-5001"))
    with pytest.raises(RuntimeError, match="Episode is already finished"):
        env.step(SelectPOAction(po_id="PO-5001"))


# ---------------------------------------------------------------------------
# PO selection tests
# ---------------------------------------------------------------------------


def test_correct_po_selection_reward():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    obs = env.step(SelectPOAction(po_id="PO-5001"))
    assert obs.reward == 0.20
    assert obs.stage == "compare_items"


def test_wrong_po_selection_gives_negative_reward_and_stage_advances():
    """Selecting a valid but wrong PO gives -0.10 but stage still advances."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    obs = env.step(SelectPOAction(po_id="PO-5099"))  # distractor PO
    assert obs.reward == -0.10
    assert obs.stage == "compare_items"


def test_invalid_po_selection_gives_zero_and_no_advance():
    """Selecting a PO not in available candidates gives 0.0 and stage does not advance."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    obs = env.step(SelectPOAction(po_id="PO-9999"))
    assert obs.reward == 0.0
    assert obs.stage == "select_po"


# ---------------------------------------------------------------------------
# Compare item tests
# ---------------------------------------------------------------------------


def test_compare_item_out_of_bounds_gives_zero():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    env.step(SelectPOAction(po_id="PO-5001"))
    obs = env.step(CompareItemAction(
        invoice_item_index=99,
        po_item_description="...",
        found_in_po=True,
        price_matches=True,
        quantity_matches=True,
    ))
    assert obs.reward == 0.0
    assert "out of range" in obs.info.get("error", "").lower()


def test_compare_item_partial_credit():
    """Exactly one boolean wrong → 0.04 partial credit."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    env.step(SelectPOAction(po_id="PO-5001"))
    # Office Chair: gt_found_in_po=True, gt_price_matches=True, gt_qty_matches=True.
    # Submit price_matches=False (wrong) → partial credit.
    obs = env.step(CompareItemAction(
        invoice_item_index=0,
        po_item_description="Office Chair",
        found_in_po=True,
        price_matches=False,   # wrong
        quantity_matches=True,
    ))
    assert obs.reward == 0.04


def test_compare_item_all_wrong_gives_zero():
    """All three booleans wrong → 0.0 reward."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    env.step(SelectPOAction(po_id="PO-5001"))
    obs = env.step(CompareItemAction(
        invoice_item_index=0,
        po_item_description="Office Chair",
        found_in_po=False,
        price_matches=False,
        quantity_matches=False,
    ))
    assert obs.reward == 0.0


# ---------------------------------------------------------------------------
# Discrepancy flag tests
# ---------------------------------------------------------------------------


def test_spurious_discrepancy_flag_penalty():
    """Flagging a discrepancy not in ground truth gives -0.05."""
    env = InvoiceReconciliationEnv()
    _advance_to_flag_discrepancies(env, "easy-exact-match", "PO-5001", 2)
    obs = env.step(FlagDiscrepancyAction(
        discrepancy_type=DiscrepancyType.PRICE_MISMATCH,  # not expected
        details="Spurious flag",
    ))
    assert obs.reward == -0.05


# ---------------------------------------------------------------------------
# Max-steps tests
# ---------------------------------------------------------------------------


def test_max_steps_terminates_episode_with_penalty():
    """Episode terminates with -0.10 penalty when max_steps reached without final_decision."""
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")  # max_steps = 8
    env.step(SelectPOAction(po_id="PO-5001"))                           # step 1
    env.step(CompareItemAction(invoice_item_index=0, po_item_description="...",
                               found_in_po=True, price_matches=True, quantity_matches=True))  # step 2
    env.step(CompareItemAction(invoice_item_index=1, po_item_description="...",
                               found_in_po=True, price_matches=True, quantity_matches=True))  # step 3
    # Use up remaining steps with spurious flags (spurious types are not deduplicated)
    spurious_types = [
        DiscrepancyType.EXTRA_CHARGE,
        DiscrepancyType.QUANTITY_MISMATCH,
        DiscrepancyType.DUPLICATE_INVOICE,
        DiscrepancyType.PARTIAL_DELIVERY,
        DiscrepancyType.MISSING_LINE_ITEM,
    ]
    obs = None
    for disc in spurious_types:
        obs = env.step(FlagDiscrepancyAction(discrepancy_type=disc, details="..."))
    assert obs is not None
    assert obs.is_done
    assert obs.info.get("max_steps_reached")


# ---------------------------------------------------------------------------
# env.state() tests
# ---------------------------------------------------------------------------


def test_state_returns_current_observation_without_reward():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    env.step(SelectPOAction(po_id="PO-5001"))
    state_obs = env.state()
    assert state_obs.stage == "compare_items"
    assert state_obs.reward == 0.0
    assert state_obs.selected_po is not None
    assert state_obs.selected_po.po_id == "PO-5001"


# ---------------------------------------------------------------------------
# Confidence / needs_review tests
# ---------------------------------------------------------------------------


def test_confidence_correct_po_is_1_and_no_review_needed():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    obs = env.step(SelectPOAction(po_id="PO-5001"))
    assert obs.confidence.get("po_selection") == 1.0
    assert obs.needs_review is False


def test_confidence_wrong_po_is_low_and_triggers_needs_review():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    obs = env.step(SelectPOAction(po_id="PO-5099"))  # wrong PO
    assert obs.confidence.get("po_selection") == 0.3
    assert obs.needs_review is True


def test_compliance_rule_present_in_observation():
    env = InvoiceReconciliationEnv()
    env.reset("compliance-soc2-vendor")
    obs = env.step(SelectPOAction(po_id="PO-7001"))
    assert obs.compliance_check == "SOC2_REQUIRED_FOR_ORDERS_OVER_5000"


def test_compliance_rule_absent_for_plain_scenario():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    obs = env.step(SelectPOAction(po_id="PO-5001"))
    assert obs.compliance_check is None


def test_action_history_tracks_actions():
    env = InvoiceReconciliationEnv()
    env.reset("easy-exact-match")
    env.step(SelectPOAction(po_id="PO-5001"))
    obs = env.step(CompareItemAction(
        invoice_item_index=0, po_item_description="...",
        found_in_po=True, price_matches=True, quantity_matches=True,
    ))
    assert len(obs.action_history) == 2
    assert obs.action_history[0]["action_type"] == "select_po"
    assert obs.action_history[1]["action_type"] == "compare_item"


# ---------------------------------------------------------------------------
# Final decision nuances
# ---------------------------------------------------------------------------


def test_no_expected_discrepancies_gives_full_disc_reward():
    """When no discrepancies exist and none are flagged, disc_reward = 0.20."""
    env = InvoiceReconciliationEnv()
    _advance_to_flag_discrepancies(env, "easy-exact-match", "PO-5001", 2)
    obs = env.step(FinalDecisionAction(
        decision="approve", matched_po_id="PO-5001", discrepancy_flags=[],
    ))
    assert obs.info["reward_breakdown"]["discrepancy_reward"] == 0.20


def test_wrong_final_decision_gives_negative_decision_reward():
    """Wrong decision (reject vs expected approve) → decision_reward = -0.30."""
    env = InvoiceReconciliationEnv()
    _advance_to_flag_discrepancies(env, "easy-exact-match", "PO-5001", 2)
    obs = env.step(FinalDecisionAction(decision="reject", matched_po_id="PO-5001"))
    assert obs.info["reward_breakdown"]["decision_reward"] == -0.30


def test_discrepancy_flags_in_final_decision_count_toward_coverage():
    """Flags submitted via discrepancy_flags in FinalDecisionAction count even without stage-3 flags."""
    env = InvoiceReconciliationEnv()
    _advance_to_flag_discrepancies(env, "hard-discrepancy-detection", "PO-5003", 3)
    # Skip stage-3 flagging; submit all flags via the final_decision action
    obs = env.step(FinalDecisionAction(
        decision="reject",
        matched_po_id="PO-5003",
        discrepancy_flags=[
            DiscrepancyType.PRICE_MISMATCH,
            DiscrepancyType.QUANTITY_MISMATCH,
            DiscrepancyType.EXTRA_CHARGE,
        ],
    ))
    assert obs.is_done
    # 3/3 expected discrepancies covered → full 0.20 disc_reward
    assert obs.info["reward_breakdown"]["discrepancy_reward"] == 0.20


def test_is_done_and_normalized_score_present_after_final_decision():
    env = InvoiceReconciliationEnv()
    _advance_to_flag_discrepancies(env, "easy-exact-match", "PO-5001", 2)
    obs = env.step(FinalDecisionAction(decision="approve", matched_po_id="PO-5001"))
    assert obs.is_done
    assert 0.0 < obs.info["normalized_score"] <= 1.0


# ---------------------------------------------------------------------------
# Full happy-path tests for the 7 untested scenarios
# ---------------------------------------------------------------------------


def test_medium_fuzzy_match_happy_path():
    obs = _full_run(
        "medium-fuzzy-match", "PO-5002", 2,
        [DiscrepancyType.VENDOR_NAME_MISMATCH, DiscrepancyType.PRICE_MISMATCH],
        "flag_discrepancy",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


def test_vat_reverse_charge_happy_path():
    obs = _full_run(
        "vat-reverse-charge", "PO-8001", 1,
        [DiscrepancyType.TAX_MISMATCH],
        "flag_discrepancy",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


def test_duplicate_invoice_detection_happy_path():
    obs = _full_run(
        "duplicate-invoice-detection", "PO-5001", 1,
        [DiscrepancyType.DUPLICATE_INVOICE],
        "reject",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


def test_partial_delivery_po_happy_path():
    obs = _full_run(
        "partial-delivery-po", "PO-5003", 1,
        [DiscrepancyType.QUANTITY_MISMATCH],
        "flag_discrepancy",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


def test_vendor_sanctions_check_happy_path():
    obs = _full_run(
        "vendor-sanctions-check", "PO-8002", 1,
        [DiscrepancyType.VENDOR_NAME_MISMATCH],
        "reject",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


def test_multi_currency_compliance_happy_path():
    obs = _full_run(
        "multi-currency-compliance", "PO-7003", 2,
        [DiscrepancyType.PRICE_MISMATCH],
        "flag_discrepancy",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


def test_ambiguous_split_invoice_happy_path():
    obs = _full_run(
        "ambiguous-split-invoice", "PO-6001", 3,
        [DiscrepancyType.PRICE_MISMATCH, DiscrepancyType.QUANTITY_MISMATCH, DiscrepancyType.EXTRA_CHARGE],
        "reject",
    )
    assert obs.is_done
    assert obs.cumulative_reward > 0


# ---------------------------------------------------------------------------
# _fuzzy_match_key unit tests
# ---------------------------------------------------------------------------


def test_fuzzy_match_key_exact_match():
    assert _fuzzy_match_key("office chair", {"office chair": 1}) == "office chair"


def test_fuzzy_match_key_partial_overlap_selects_best():
    result = _fuzzy_match_key("ergonomic office chair", {"office chair": 1, "desk lamp": 2})
    assert result == "office chair"


def test_fuzzy_match_key_no_common_words_returns_none():
    assert _fuzzy_match_key("widget xyz", {"office chair": 1}) is None


def test_fuzzy_match_key_empty_candidates_returns_none():
    assert _fuzzy_match_key("office chair", {}) is None


def test_fuzzy_match_key_chooses_highest_overlap():
    candidates = {"laptop model x": 1, "laptop model y": 2, "wireless mouse": 3}
    result = _fuzzy_match_key("laptop model x pro", candidates)
    assert result == "laptop model x"  # 3 words overlap vs 2


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_health_endpoint_returns_healthy():
    from server.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_tasks_endpoint_returns_total_and_curriculum():
    from server.main import app
    from fastapi.testclient import TestClient
    client = TestClient(app)
    resp = client.get("/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 10
    assert "curriculum" in data
    assert len(data["curriculum"]) == 10
