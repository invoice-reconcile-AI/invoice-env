"""Invoice Reconciliation Agent.

Connects to the running OpenEnv server, receives an InvoiceObservation,
and decides the correct action (approve / reject / flag_discrepancy / etc.)
using an LLM with structured output.

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
from pathlib import Path
from typing import Any

import requests

# Load .env file automatically (no-op if python-dotenv not installed or .env missing)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL    = os.getenv("ENV_BASE_URL",  "http://127.0.0.1:8000")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "together")   # "together" | "groq" | "openai"
LLM_MODEL   = os.getenv("LLM_MODEL",    "meta-llama/Llama-3.3-70B-Instruct-Turbo")
LLM_API_KEY = os.getenv("LLM_API_KEY",  "")

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
# LLM system prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Accounts-Payable reconciliation agent.
You will be given an invoice, a purchase order (PO), and a goods-received note (GRN).
Your job is to carefully compare all three documents, detect every discrepancy, and decide the correct action.

Decision Logic (scored 0.0-1.0):
1. action_type (0.5 pts):
   - "approve"          — ONLY if everything matches perfectly (prices, quantities, vendor).
   - "flag_discrepancy" — minor issues only: small price delta (<=5) OR fuzzy vendor name only.
   - "reject"           — serious issues: large overcharge, quantity billed > received, extra items, multiple issues.
2. matched_po_id (0.2 pts): Provide the exact PO ID from the purchase_order field.
3. reasoning (0.3 pts): Mention specific discrepancy keywords:
   price_mismatch, quantity_mismatch, vendor_name_mismatch, extra_charge, missing_line_item, etc.
   For "approve": do NOT use mismatch/error/wrong/missing keywords.

Respond ONLY with a valid JSON object — no markdown, no extra text:
{
  "action_type": "<approve|reject|flag_discrepancy>",
  "discrepancy_flags": ["<price_mismatch|quantity_mismatch|vendor_name_mismatch|extra_charge|...>"],
  "matched_po_id": "<po_id string>",
  "reasoning": "<concise explanation citing specific items, prices, quantities>"
}
""".strip()


# ---------------------------------------------------------------------------
# Observation formatter — uses the ACTUAL InvoiceObservation schema
# (invoice, purchase_order, goods_received_note — all flat fields)
# ---------------------------------------------------------------------------

def _format_observation(obs: dict[str, Any]) -> str:
    """Pretty-format the observation for the LLM prompt."""
    lines: list[str] = []

    # ── Invoice ──────────────────────────────────────────────────────────
    inv = obs.get("invoice") or {}
    lines.append("=== INVOICE ===")
    lines.append(f"  ID           : {inv.get('invoice_id')}")
    lines.append(f"  Vendor       : {inv.get('vendor_name')}")
    lines.append(f"  Date         : {inv.get('invoice_date')}")
    lines.append(f"  PO Reference : {inv.get('po_reference')}")
    lines.append(f"  Subtotal     : {inv.get('subtotal')} {inv.get('currency')}")
    lines.append(f"  Tax          : {inv.get('tax')}")
    lines.append(f"  Total        : {inv.get('total_amount')} {inv.get('currency')}")
    lines.append("  Line Items Billed:")
    for item in inv.get("line_items") or []:
        lines.append(
            f"    - {item.get('description', ''):35s}  "
            f"qty={item.get('quantity')}  "
            f"unit=${item.get('unit_price')}  "
            f"total=${item.get('total')}"
        )

    # ── Purchase Order ────────────────────────────────────────────────────
    po = obs.get("purchase_order")
    if po:
        lines.append("\n=== PURCHASE ORDER ===")
        lines.append(f"  PO ID        : {po.get('po_id')}")
        lines.append(f"  Vendor       : {po.get('vendor_name')}")
        lines.append(f"  Issue Date   : {po.get('issue_date')}")
        lines.append(f"  Approved By  : {po.get('approved_by')}")
        lines.append(f"  Total        : {po.get('total_amount')} {po.get('currency')}")
        lines.append("  Line Items Ordered:")
        for item in po.get("line_items") or []:
            lines.append(
                f"    - {item.get('description', ''):35s}  "
                f"qty={item.get('quantity')}  "
                f"unit=${item.get('unit_price')}  "
                f"total=${item.get('total')}"
            )
    else:
        lines.append("\n=== PURCHASE ORDER === (none found)")

    # ── Goods Received Note ───────────────────────────────────────────────
    grn = obs.get("goods_received_note")
    if grn:
        lines.append("\n=== GOODS RECEIVED NOTE ===")
        lines.append(f"  GRN ID       : {grn.get('grn_id')}")
        lines.append(f"  PO ID        : {grn.get('po_id')}")
        lines.append(f"  Received     : {grn.get('received_date')}")
        lines.append(f"  Received By  : {grn.get('received_by')}")
        lines.append("  Items Received:")
        for item in grn.get("items_received") or []:
            lines.append(
                f"    - {item.get('description', ''):35s}  "
                f"qty={item.get('quantity')}  "
                f"unit=${item.get('unit_price')}  "
                f"total=${item.get('total')}"
            )
    else:
        lines.append("\n=== GOODS RECEIVED NOTE === (none)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(observation_text: str) -> dict[str, Any]:
    """Call the configured LLM and return a parsed action dict."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": observation_text},
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
    import re
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {}


def _call_together(messages: list[dict]) -> dict[str, Any]:
    from together import Together
    client = Together(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL, messages=messages, temperature=0.0, max_tokens=512,
    )
    return _parse_llm_response(resp.choices[0].message.content)


def _call_groq(messages: list[dict]) -> dict[str, Any]:
    from groq import Groq
    client = Groq(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL, messages=messages, temperature=0.0, max_tokens=512,
    )
    return _parse_llm_response(resp.choices[0].message.content)


def _call_openai(messages: list[dict]) -> dict[str, Any]:
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL, messages=messages, temperature=0.0, max_tokens=512,
        response_format={"type": "json_object"},
    )
    return _parse_llm_response(resp.choices[0].message.content)


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run_task(task_id: str) -> dict[str, Any]:
    """Run one complete episode for *task_id* and return the scorecard dict."""
    print(f"\n{'='*60}")
    print(f"  TASK : {task_id}")
    print(f"{'='*60}")

    # 1. Reset env — returns InvoiceObservation
    obs = reset_env(task_id)
    print(f"[env]  Episode started -> episode_id: {obs.get('episode_id')}")

    # 2. Format observation for LLM
    obs_text = _format_observation(obs)
    print(f"\n[obs]\n{obs_text}\n")

    # 3. Ask LLM for action
    print("[llm]  Calling LLM ...")
    raw_action = call_llm(obs_text)
    print(f"[llm]  Response: {json.dumps(raw_action, indent=2)}")

    # 4. Validate + normalise action fields
    raw_action.setdefault("discrepancy_flags", [])
    raw_action.setdefault("reasoning", "")

    # Fallback po_id from observation if LLM didn't provide one
    po = obs.get("purchase_order") or {}
    fallback_po_id = po.get("po_id")
    if not raw_action.get("matched_po_id"):
        raw_action["matched_po_id"] = fallback_po_id

    action_type = str(raw_action.get("action_type") or "flag_discrepancy").strip().lower()
    if action_type not in VALID_ACTIONS:
        print(f"[warn] Invalid action_type '{action_type}' — defaulting to 'flag_discrepancy'")
        action_type = "flag_discrepancy"

    action = {
        "action_type":       action_type,
        "matched_po_id":     raw_action.get("matched_po_id"),
        "discrepancy_flags": [f for f in raw_action["discrepancy_flags"] if f in VALID_DISCREPANCIES],
        "reasoning":         raw_action.get("reasoning", ""),
    }

    # 5. Submit to env — returns InvoiceObservation
    result_obs = step_env(action)

    # Score and info live in result_obs["reward"] and result_obs["info"]
    score  = float(result_obs.get("reward", 0.0))
    info   = result_obs.get("info") or {}
    result = info.get("result", "unknown")
    reason = info.get("reason", "")
    is_correct = bool(info.get("correct_decision_made", False))

    scorecard = {
        "score":                       score,
        "result":                      result,
        "correct_decision_made":       is_correct,
        "correct_po_identified":       info.get("correct_po_identified"),
        "discrepancy_correctly_noted": info.get("discrepancy_correctly_noted"),
        "reason":                      reason,
    }

    print(f"\n[env]  Score={score:.2f}  result={result}  DecisionCorrect={is_correct}")
    print(f"[env]  Reason: {reason}")
    print(f"SCORECARD_JSON: {json.dumps(scorecard)}")

    return scorecard


def run_all_tasks() -> None:
    tasks = ["easy-exact-match", "medium-fuzzy-match", "hard-discrepancy-detection"]
    results: list[dict] = []
    for task_id in tasks:
        final = run_task(task_id)
        results.append({
            "task_id":          task_id,
            "score":            final.get("score", 0.0),
            "decision_correct": final.get("correct_decision_made", False),
            "result":           final.get("result", "?"),
        })

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    total = 0.0
    for r in results:
        score = r["score"]
        if score >= 1.0:
            icon = "[PASS]"
        elif score >= 0.5:
            icon = "[WARN]"
        else:
            icon = "[FAIL]"
        print(f"  {icon}  {r['task_id']:35s}  score={score:.2f}  result={r['result']}  correct={r['decision_correct']}")
        total += score
    n = len(tasks)
    print(f"\n  Total score: {total:.2f} / {float(n):.1f}  (avg: {total/n:.2f})")
    print(f"  Tasks passed (>=0.8): {sum(1 for r in results if r['score'] >= 0.8)}/{n}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoice Reconciliation Agent -- powered by Llama / Meta AI"
    )
    parser.add_argument("--task", default="all", help="Task to run (default: all)")
    parser.add_argument("--base-url", default=None, help="Override ENV_BASE_URL")
    parser.add_argument("--provider", default=None, choices=["together", "groq", "openai"],
                        help="Override LLM_PROVIDER env var")
    parser.add_argument("--model", default=None, help="Override LLM_MODEL env var")
    args = parser.parse_args()

    global BASE_URL, LLM_PROVIDER, LLM_MODEL
    if args.base_url:  BASE_URL     = args.base_url
    if args.provider:  LLM_PROVIDER = args.provider
    if args.model:     LLM_MODEL    = args.model

    if not LLM_API_KEY:
        print("[warn] LLM_API_KEY is not set. Set it in .env or the environment.")

    if args.task == "all":
        run_all_tasks()
    else:
        run_task(args.task)


if __name__ == "__main__":
    main()
