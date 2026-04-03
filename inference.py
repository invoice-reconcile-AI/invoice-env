"""Inference script for the Invoice Reconciliation OpenEnv environment.

Connects to the running FastAPI env server, resets an episode per task,
calls an LLM to decide the correct action, submits it, and prints the
mandatory log lines required by the OpenEnv benchmark harness:

    [START] task=<id> env=<benchmark> model=<model>
    [STEP]  step=<n> action=<json> reward=<r> done=<bool> info=<json>
    [END]   success=<bool> steps=<n> rewards=<csv>

Plus the SCORECARD_JSON line read by evaluator.py.

Required environment variables (see .env):
    ENV_BASE_URL   – FastAPI server base URL  (default: http://localhost:8000)
    LLM_PROVIDER   – "together" | "groq" | "openai"  (default: together)
    LLM_MODEL      – model identifier
    LLM_API_KEY    – API key for the chosen provider

Usage:
    python inference.py                          # run all three tasks
    python inference.py --task easy-exact-match  # run one task
    python inference.py --task all               # explicit all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Load .env automatically
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENV_BASE_URL  = os.getenv("ENV_BASE_URL",  "http://localhost:8000")
LLM_PROVIDER  = os.getenv("LLM_PROVIDER",  "together")
LLM_MODEL     = os.getenv("LLM_MODEL",     "meta-llama/Llama-3.3-70B-Instruct-Turbo")
LLM_API_KEY   = os.getenv("LLM_API_KEY",   "")

BENCHMARK         = "InvoiceReconciliationBenchmark-v1"
SUCCESS_THRESHOLD = 0.8   # score >= this → success

ALL_TASKS: List[str] = [
    "easy-exact-match",
    "medium-fuzzy-match",
    "hard-discrepancy-detection",
]

VALID_ACTION_TYPES = {"approve", "reject", "flag_discrepancy",
                      "request_credit_note", "escalate", "match_to_po"}

VALID_DISCREPANCY_FLAGS = {
    "price_mismatch", "quantity_mismatch", "vendor_name_mismatch",
    "po_not_found", "duplicate_invoice", "partial_delivery",
    "extra_charge", "missing_line_item",
}

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _bool_str(v: bool) -> str:
    return "true" if v else "false"


def log_start(task: str, model: str) -> None:
    print(f"[START] task={task} env={BENCHMARK} model={model}", flush=True)


def log_step(step: int, action: Dict[str, Any], reward: float,
             done: bool, info: Any) -> None:
    action_field = json.dumps(action, ensure_ascii=True, separators=(",", ":"))
    info_field   = json.dumps(info,   ensure_ascii=True, separators=(",", ":"))
    print(
        f"[STEP] step={step} action={action_field} "
        f"reward={reward:.2f} done={_bool_str(done)} info={info_field}",
        flush=True,
    )


def log_end(success: bool, steps: int, rewards: List[float]) -> None:
    rewards_csv = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={_bool_str(success)} steps={steps} rewards={rewards_csv}",
          flush=True)

# ---------------------------------------------------------------------------
# Environment HTTP client
# ---------------------------------------------------------------------------

def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = requests.post(f"{ENV_BASE_URL}{path}", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def env_reset(task_id: str) -> Dict[str, Any]:
    return _post("/reset", {"task_id": task_id})


def env_step(action: Dict[str, Any]) -> Dict[str, Any]:
    return _post("/step", action)

# ---------------------------------------------------------------------------
# System prompt — tuned for exact 0.5 + 0.2 + 0.3 scoring rubric
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert Accounts-Payable reconciliation agent.

You will receive a JSON object containing:
  - invoice      : full invoice data (vendor, dates, line_items, po_reference, etc.)
  - purchase_order: the matched Purchase Order (po_id, vendor, line_items, totals)
  - goods_received_note: GRN confirming physical delivery (items_received with quantities)

DECISION RULES:
1. Match the invoice vendor name to the PO vendor name (case-insensitive, ignore punctuation).
2. Compare EVERY invoice line item to the PO line items:
     - unit_price must match exactly → flag price_mismatch if different.
     - quantity invoiced must equal quantity in GRN → flag quantity_mismatch if different.
     - invoice item absent from PO → flag extra_charge.
     - PO item absent from invoice → flag missing_line_item.
3. Choose ONE action_type:
     "approve"           — ALL prices, quantities, vendor name match perfectly. No extras.
     "flag_discrepancy"  — Minor issues only: small price delta (≤$5) OR fuzzy vendor name mismatch ONLY.
     "reject"            — Serious issues: large price overcharge, quantity invoiced > received,
                           extra line items not in PO, or MULTIPLE simultaneous discrepancies.

SCORING BREAKDOWN (maximise all three):
  +0.5  Correct action_type (approve / flag_discrepancy / reject)
  +0.2  Correct matched_po_id linked
  +0.3  Reasoning mentions specific discrepancy keywords:
          price_mismatch, quantity_mismatch, extra_charge, vendor_name_mismatch,
          missing_line_item, po_not_found, duplicate_invoice, partial_delivery
        For "approve": do NOT use negative keywords like mismatch, error, wrong, missing, discrepancy.

Respond with ONLY a valid JSON object — no markdown, no prose:
{
  "action_type":        "<approve|flag_discrepancy|reject>",
  "matched_po_id":      "<PO ID string from purchase_order.po_id>",
  "discrepancy_flags":  ["<zero or more from VALID_DISCREPANCY_FLAGS>"],
  "reasoning":          "<concise explanation — cite specific item names, exact prices, quantities>"
}

VALID_DISCREPANCY_FLAGS:
  price_mismatch, quantity_mismatch, vendor_name_mismatch,
  po_not_found, duplicate_invoice, partial_delivery, extra_charge, missing_line_item
""".strip()

# ---------------------------------------------------------------------------
# Prompt builder — formats the full observation for the LLM
# ---------------------------------------------------------------------------

def _build_user_prompt(obs: Dict[str, Any]) -> str:
    """Convert the raw observation dict into a clean, structured LLM prompt."""
    inv = obs.get("invoice", {})

    invoice_section = {
        "invoice_id":       inv.get("invoice_id"),
        "vendor_name":      inv.get("vendor_name"),
        "invoice_date":     inv.get("invoice_date"),
        "due_date":         inv.get("due_date"),
        "subtotal":         inv.get("subtotal"),
        "tax":              inv.get("tax"),
        "total_amount":     inv.get("total_amount"),
        "currency":         inv.get("currency"),
        "line_items":       inv.get("line_items", []),
        "po_reference":     inv.get("po_reference"),
        "notes":            inv.get("notes"),
    }

    po = obs.get("purchase_order")
    po_section = None
    if po:
        po_section = {
            "po_id":         po.get("po_id"),
            "vendor_name":   po.get("vendor_name"),
            "issue_date":    str(po.get("issue_date")),
            "approved_by":   po.get("approved_by"),
            "total_amount":  po.get("total_amount"),
            "currency":      po.get("currency"),
            "line_items":    po.get("line_items", []),
        }

    grn = obs.get("goods_received_note")
    grn_section = None
    if grn:
        grn_section = {
            "grn_id":         grn.get("grn_id"),
            "po_id":          grn.get("po_id"),
            "received_date":  str(grn.get("received_date")),
            "items_received": grn.get("items_received", []),
            "received_by":    grn.get("received_by"),
            "notes":          grn.get("notes"),
        }

    payload = {
        "task_id":             obs.get("task_id"),
        "step":                obs.get("step"),
        "invoice":             invoice_section,
        "purchase_order":      po_section,
        "goods_received_note": grn_section,
        "allowed_actions":     ["approve", "flag_discrepancy", "reject"],
        "allowed_discrepancy_flags": sorted(VALID_DISCREPANCY_FLAGS),
    }

    return json.dumps(payload, ensure_ascii=True, default=str, indent=2)

# ---------------------------------------------------------------------------
# JSON extraction — handles fenced and raw JSON from LLM
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        text = "\n".join(inner).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find first {...} block
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}

# ---------------------------------------------------------------------------
# Action normalization — maps LLM output to the exact InvoiceAction schema
# ---------------------------------------------------------------------------

def _normalize_action(raw: Dict[str, Any], fallback_po_id: Optional[str]) -> Dict[str, Any]:
    # action_type — accept aliases from other prompt formats
    action_type = str(
        raw.get("action_type") or raw.get("decision") or "flag_discrepancy"
    ).strip().lower()
    if action_type not in VALID_ACTION_TYPES:
        action_type = "flag_discrepancy"

    # matched_po_id
    raw_po_id = raw.get("matched_po_id") or raw.get("po_id")
    matched_po_id = str(raw_po_id).strip() if raw_po_id else fallback_po_id

    # discrepancy_flags — filter to only known values
    flags = [
        f.strip().lower()
        for f in (raw.get("discrepancy_flags") or [])
        if isinstance(f, str) and f.strip().lower() in VALID_DISCREPANCY_FLAGS
    ]

    # reasoning — accept 'note' alias, truncate to avoid log bloat
    reasoning = str(raw.get("reasoning") or raw.get("note") or "").strip()
    if len(reasoning) > 500:
        reasoning = reasoning[:500]

    return {
        "action_type":       action_type,
        "matched_po_id":     matched_po_id,
        "discrepancy_flags": flags,
        "reasoning":         reasoning,
    }

# ---------------------------------------------------------------------------
# LLM call — supports Together AI, Groq, OpenAI
# ---------------------------------------------------------------------------

def _call_together(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    from together import Together
    client = Together(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=400,
    )
    return _extract_json(resp.choices[0].message.content or "")


def _call_groq(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    from groq import Groq
    client = Groq(api_key=LLM_API_KEY or None)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=400,
    )
    return _extract_json(resp.choices[0].message.content or "")


def _call_openai(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    from openai import OpenAI
    client = OpenAI(api_key=LLM_API_KEY or None, base_url=None)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    return _extract_json(resp.choices[0].message.content or "")


def call_llm(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Build prompt, call configured LLM, return raw parsed dict."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": _build_user_prompt(obs)},
    ]
    provider = LLM_PROVIDER.lower()
    if provider == "together":
        return _call_together(messages)
    elif provider == "groq":
        return _call_groq(messages)
    elif provider == "openai":
        return _call_openai(messages)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER!r}")

# ---------------------------------------------------------------------------
# Single task runner
# ---------------------------------------------------------------------------

def run_task(task_id: str) -> Dict[str, Any]:
    """Run one complete episode and return the reward info dict."""
    rewards: List[float] = []
    step_count = 0
    success = False
    reward_data: Dict[str, Any] = {}

    log_start(task=task_id, model=LLM_MODEL)

    try:
        # ── 1. Reset environment ──────────────────────────────────────────────
        obs = env_reset(task_id)
        print(f"[info] episode_id={obs.get('episode_id')}  task={task_id}", flush=True)

        # ── 2. Derive fallback PO ID for error recovery ───────────────────────
        po = obs.get("purchase_order") or {}
        fallback_po_id: Optional[str] = po.get("po_id") if po else None

        # ── 3. LLM decision ───────────────────────────────────────────────────
        print("[llm]  Calling LLM ...", flush=True)
        raw_llm = call_llm(obs)
        print(f"[llm]  Raw: {json.dumps(raw_llm, indent=2)}", flush=True)

        # Handle empty/failed parse
        if not raw_llm:
            raw_llm = {
                "action_type":       "flag_discrepancy",
                "matched_po_id":     fallback_po_id,
                "discrepancy_flags": [],
                "reasoning": "LLM returned unparseable response; defaulting to flag_discrepancy.",
            }

        action = _normalize_action(raw_llm, fallback_po_id)

        # ── 4. Submit action to environment ───────────────────────────────────
        result_obs = env_step(action)

        step_count = 1
        score  = float(result_obs.get("reward", 0.0))
        done   = bool(result_obs.get("is_done", True))
        info   = result_obs.get("info", {})
        rewards.append(score)

        # Build reward_data from the observation's info dict for SCORECARD_JSON
        reward_data = {
            "score":                      score,
            "correct_decision_made":      info.get("correct_decision_made"),
            "correct_po_identified":      info.get("correct_po_identified"),
            "discrepancy_correctly_noted": info.get("discrepancy_correctly_noted"),
            "reason":                     info.get("reason"),
            "result":                     info.get("result"),
        }

        log_step(
            step=step_count,
            action=action,
            reward=score,
            done=done,
            info={
                "result":                      info.get("result"),
                "correct_decision_made":       info.get("correct_decision_made"),
                "correct_po_identified":       info.get("correct_po_identified"),
                "discrepancy_correctly_noted": info.get("discrepancy_correctly_noted"),
                "reason":                      info.get("reason"),
            },
        )

        success = done and score >= SUCCESS_THRESHOLD

    except requests.exceptions.ConnectionError:
        print(
            f"[ERROR] Cannot reach env server at {ENV_BASE_URL}. "
            "Is 'uvicorn server.main:app' running?",
            flush=True,
        )
    except Exception as exc:
        print(f"[ERROR] Unexpected error in task '{task_id}': {exc}", flush=True)

    log_end(success=success, steps=step_count, rewards=rewards)

    # Emit SCORECARD_JSON so evaluator.py can parse it
    print(f"SCORECARD_JSON: {json.dumps(reward_data)}", flush=True)

    return reward_data


# ---------------------------------------------------------------------------
# Multi-task runner
# ---------------------------------------------------------------------------

def run_all_tasks() -> None:
    results: List[Dict[str, Any]] = []
    for task_id in ALL_TASKS:
        rd = run_task(task_id)
        results.append({"task_id": task_id, **rd})
        print()  # blank line separator between tasks

    # ── Summary ────────────────────────────────────────────────────────────
    print("=" * 60, flush=True)
    print("  SUMMARY", flush=True)
    print("=" * 60, flush=True)
    total_score = 0.0
    for r in results:
        score   = r.get("score", 0.0)
        correct = r.get("correct_decision_made", False)
        result  = r.get("result", "?")
        if score >= 1.0:
            icon = "[PASS]"
        elif score >= 0.5:
            icon = "[WARN]"
        else:
            icon = "[FAIL]"
        print(f"  {icon}  {r['task_id']:<35s}  score={score:.2f}  result={result}  decision_correct={correct}")
        total_score += score
    n = len(results)
    avg = total_score / n if n else 0.0
    print(f"\n  Total: {total_score:.2f} / {float(n):.1f}   avg: {avg:.2f}", flush=True)
    successes = sum(1 for r in results if r.get("score", 0.0) >= SUCCESS_THRESHOLD)
    print(f"  Tasks passed (>={SUCCESS_THRESHOLD}): {successes}/{n}", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoice Reconciliation inference script"
    )
    parser.add_argument(
        "--task",
        default="all",
        help=(
            "Task to run. Use 'all' for all three, or one of: "
            + ", ".join(ALL_TASKS)
        ),
    )
    parser.add_argument("--base-url",  default=None, help="Override ENV_BASE_URL")
    parser.add_argument("--provider",  default=None, choices=["together", "groq", "openai"],
                        help="Override LLM_PROVIDER")
    parser.add_argument("--model",     default=None, help="Override LLM_MODEL")
    args = parser.parse_args()

    global ENV_BASE_URL, LLM_PROVIDER, LLM_MODEL
    if args.base_url:  ENV_BASE_URL = args.base_url
    if args.provider:  LLM_PROVIDER = args.provider
    if args.model:     LLM_MODEL    = args.model

    if not LLM_API_KEY:
        print("[warn] LLM_API_KEY is not set — set it in .env or the environment.",
              flush=True)

    if args.task == "all":
        run_all_tasks()
    else:
        run_task(args.task)


if __name__ == "__main__":
    main()
