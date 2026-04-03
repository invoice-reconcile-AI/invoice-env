"""Invoice Reconciliation Agent.

Connects to the running OpenEnv server, receives an InvoiceObservation,
and decides the correct action (approve / reject / flag_discrepancy / etc.)
using an LLM with structured tool-call output.

Usage:
    python -m agent.agent --task easy-exact-match
    python -m agent.agent --task medium-fuzzy-match
    python -m agent.agent --task hard-discrepancy-detection
    python -m agent.agent --task all          # run all three tasks
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("ENV_BASE_URL", "http://127.0.0.1:8000")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "together")   # "together" | "groq" | "openai"
LLM_MODEL = os.getenv(
    "LLM_MODEL",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",          # Together AI default
)
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

VALID_ACTIONS = ["approve", "reject", "flag_discrepancy",
                 "request_credit_note", "escalate", "match_to_po"]
VALID_DISCREPANCIES = [
    "price_mismatch", "quantity_mismatch", "vendor_name_mismatch",
    "po_not_found", "duplicate_invoice", "partial_delivery",
    "extra_charge", "missing_line_item",
]

# ---------------------------------------------------------------------------
# Environment client helpers
# ---------------------------------------------------------------------------

def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = requests.post(f"{BASE_URL}{path}", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def reset_env(task_id: str) -> dict[str, Any]:
    """Start a fresh episode and return the first observation."""
    return _post("/reset", {"task_id": task_id})


def step_env(action: dict[str, Any]) -> dict[str, Any]:
    """Submit an action and return the resulting observation."""
    return _post("/step", action)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Accounts-Payable reconciliation agent.
You will be given an invoice, a candidate purchase order (PO), and a goods-received note (GRN).
Your job is to carefully compare all three documents, detect every discrepancy, and decide the correct action.

Decision Logic (Graded on 0.0-1.0 scale):
1. Decision Type (0.5 pts): 
   - Choose 'approve' (pay) ONLY if everything matches perfectly.
   - Choose 'flag_discrepancy' (hold) for minor issues (fuzzy name mismatch, small price diff).
   - Choose 'reject' (flag) for serious issues (missing items, major overcharge).
2. PO Identification (0.2 pts): Correctly link the PO ID in the matched_po_id field.
3. Reasoning (0.3 pts): Provide a concise but detailed explanation in the 'reasoning' field identifying EXACTLY what is wrong or why it matches. Mention specific items, prices, or names.

Respond ONLY with a valid JSON object in exactly this shape:
{
  "action_type": "<approve|reject|flag_discrepancy|request_credit_note|escalate|match_to_po>",
  "discrepancy_flags": ["<price_mismatch|quantity_mismatch|vendor_name_mismatch|po_not_found|etc>"],
  "matched_po_id": "<po_id string or null>",
  "reasoning": "<detect the specific issues here!>"
}
""".strip()


def _format_observation(obs: dict[str, Any]) -> str:
    """Pretty-format the observation for the LLM prompt."""
    lines: list[str] = []

    inv = obs.get("invoice", {})
    lines.append("=== INVOICE ===")
    lines.append(f"  ID         : {inv.get('invoice_id')}")
    lines.append(f"  Vendor     : {inv.get('vendor_name')}")
    lines.append(f"  Date       : {inv.get('invoice_date')}")
    lines.append(f"  Due Date   : {inv.get('due_date')}")
    lines.append(f"  Total      : {inv.get('total_amount')} {inv.get('currency')}")
    lines.append("  Items Billed :")
    for name, qty in (inv.get("items_billed") or {}).items():
        lines.append(f"    - {name:30s}  qty={qty}")
    lines.append("  Raw Content:")
    lines.append("-" * 40)
    for line in inv.get("raw_text_content", "").splitlines():
        lines.append(f"| {line}")
    lines.append("-" * 40)

    candidate_pos = obs.get("candidate_pos") or []
    if candidate_pos:
        lines.append("\n=== PURCHASE ORDER CANDIDATES ===")
        for idx, po in enumerate(candidate_pos):
            lines.append(f"--- PO [{idx + 1}/{len(candidate_pos)}] ---")
            lines.append(f"  PO ID          : {po.get('po_id')}")
            lines.append(f"  Vendor         : {po.get('vendor_name')}")
            lines.append(f"  Issue Date     : {po.get('issue_date')}")
            lines.append(f"  Status         : {po.get('status')}")
            lines.append(f"  Payment Terms  : {po.get('payment_terms')}")
            lines.append(f"  Total          : {po.get('total_amount')} {po.get('currency')}")
            lines.append("  Items Ordered (summary) :")
            for name, qty in (po.get("items_ordered") or {}).items():
                lines.append(f"    - {name:30s}  qty={qty}")

    grn_log = obs.get("grn_log") or []
    if grn_log:
        lines.append("\n=== GOODS RECEIVED NOTES LOG ===")
        for idx, grn in enumerate(grn_log):
            lines.append(f"--- GRN [{idx + 1}/{len(grn_log)}] ---")
            lines.append(f"  GRN ID        : {grn.get('grn_id')}")
            lines.append(f"  PO ID         : {grn.get('po_id')}")
            lines.append(f"  Received Date : {grn.get('received_date')}")
            lines.append("  Items Received :")
            for item in grn.get("items_received", []):
                lines.append(
                    f"    - {item['description']:30s}  qty={item['quantity']}  "
                    f"unit=${item['unit_price']}  total=${item['total']}"
                )

    return "\n".join(lines)


def call_llm(observation_text: str) -> dict[str, Any]:
    """Call the configured LLM and return a parsed action dict."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": observation_text},
    ]

    if LLM_PROVIDER == "together":
        return _call_together(messages)
    elif LLM_PROVIDER == "groq":
        return _call_groq(messages)
    elif LLM_PROVIDER == "openai":
        return _call_openai(messages)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")


def _parse_llm_response(raw: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON from LLM output."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first and last fence lines
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)


def _call_together(messages: list[dict]) -> dict[str, Any]:
    from together import Together  # pip install together
    client = Together(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=512,
    )
    return _parse_llm_response(resp.choices[0].message.content)


def _call_groq(messages: list[dict]) -> dict[str, Any]:
    from groq import Groq  # pip install groq
    client = Groq(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=512,
    )
    return _parse_llm_response(resp.choices[0].message.content)


def _call_openai(messages: list[dict]) -> dict[str, Any]:
    from openai import OpenAI  # pip install openai
    client = OpenAI(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    return _parse_llm_response(resp.choices[0].message.content)


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run_task(task_id: str) -> dict[str, Any]:
    """Run one complete episode for *task_id* and return the final observation."""
    print(f"\n{'='*60}")
    print(f"  TASK : {task_id}")
    print(f"{'='*60}")

    # 1. Reset env
    obs = reset_env(task_id)
    print(f"[env]  Episode started  ->  episode_id: {obs['episode_id']}")

    # 2. Format observation for LLM
    obs_text = _format_observation(obs)
    print(f"\n[obs]\n{obs_text}\n")

    # 3. Ask LLM for action
    print("[llm]  Calling LLM …")
    action = call_llm(obs_text)
    print(f"[llm]  Response: {json.dumps(action, indent=2)}")

    # 4. Validate action fields
    action.setdefault("discrepancy_flags", [])
    action.setdefault("matched_po_id", None)
    action.setdefault("reasoning", "")

    if action["action_type"] not in VALID_ACTIONS:
        print(f"[warn] Invalid action_type '{action['action_type']}' — defaulting to 'escalate'")
        action["action_type"] = "escalate"

    action["discrepancy_flags"] = [
        f for f in action["discrepancy_flags"] if f in VALID_DISCREPANCIES
    ]

    # 5. Submit to env
    reward_data = step_env(action)
    score = reward_data["score"]
    reason = reward_data["reason"]
    is_correct = reward_data["correct_decision_made"]

    print(f"\n[env]  Score={score:.2f}  DecisionCorrect={is_correct}")
    print(f"[env]  Reason: {reason}")
    
    # Also print the raw JSON for the evaluator to parse more easily
    print(f"SCORECARD_JSON: {json.dumps(reward_data)}")

    return reward_data


def run_all_tasks() -> None:
    tasks = ["easy-exact-match", "medium-fuzzy-match", "hard-discrepancy-detection"]
    results: list[dict] = []
    for task_id in tasks:
        final = run_task(task_id)
        results.append({
            "task_id": task_id,
            "reward": final["reward"],
            "result": final["info"].get("result"),
        })

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    total = 0.0
    for r in results:
        icon = "✅" if r["result"] == "correct" else ("⚠️" if r["result"] == "partial" else "❌")
        print(f"  {icon}  {r['task_id']:35s}  reward={r['reward']:+.1f}  ({r['result']})")
        total += r["reward"]
    print(f"\n  Total reward: {total:+.1f} / {len(tasks):.1f}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoice Reconciliation Agent — powered by Llama / Meta AI"
    )
    parser.add_argument(
        "--task",
        default="all",
        help="Task to run (default: all)",
    )
    parser.add_argument("--base-url", default=None,
                        help="Override ENV_BASE_URL (default: http://localhost:8000)")
    parser.add_argument("--provider", default=None,
                        choices=["together", "groq", "openai"],
                        help="Override LLM_PROVIDER env var")
    parser.add_argument("--model", default=None,
                        help="Override LLM_MODEL env var")
    args = parser.parse_args()

    global BASE_URL, LLM_PROVIDER, LLM_MODEL
    if args.base_url:
        BASE_URL = args.base_url
    if args.provider:
        LLM_PROVIDER = args.provider
    if args.model:
        LLM_MODEL = args.model

    if not LLM_API_KEY:
        print("[warn] LLM_API_KEY is not set. Set it via the environment variable.")

    if args.task == "all":
        run_all_tasks()
    else:
        run_task(args.task)


if __name__ == "__main__":
    main()
