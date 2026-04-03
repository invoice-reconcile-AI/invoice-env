"""Simple smoke test for the Invoice Reconciliation environment."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import Decision, InvoiceReconciliationAction
from server.environment import InvoiceReconciliationEnvironment


def _po_from_invoice_text(invoice_text: str, fallback_po_id: str) -> str:
    match = re.search(r"PO-\d+", invoice_text)
    return match.group(0) if match else fallback_po_id


def main() -> None:
    env = InvoiceReconciliationEnvironment()
    tasks = [
        "easy-exact-match",
        "medium-fuzzy-tolerance",
        "hard-discrepancy-detection",
    ]

    decision_map = {
        "easy-exact-match": Decision.PAY,
        "medium-fuzzy-tolerance": Decision.PAY,
        "hard-discrepancy-detection": Decision.FLAG,
    }

    note_map = {
        "easy-exact-match": "Invoice and PO match. Approved for payment.",
        "medium-fuzzy-tolerance": "Within tolerance due to rounding and tax.",
        "hard-discrepancy-detection": "Flag for price mismatch and quantity mismatch.",
    }

    for task in tasks:
        first = env.reset(task_id=task)
        guessed_po = _po_from_invoice_text(
            first.invoice_text, first.candidate_pos[0].po_id
        )

        second = env.step(
            InvoiceReconciliationAction(
                po_id=guessed_po,
                decision=Decision.HOLD,
                note="Initial PO linkage pass.",
            )
        )
        assert not second.done

        final = env.step(
            InvoiceReconciliationAction(
                po_id=guessed_po,
                decision=decision_map[task],
                note=note_map[task],
            )
        )
        assert final.done
        assert 0.0 <= final.accumulated_score <= 1.0

    print("Smoke test passed for all tasks.")


if __name__ == "__main__":
    main()
