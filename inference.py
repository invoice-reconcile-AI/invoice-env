"""Inference script for the Invoice Reconciliation OpenEnv environment – multi-step edition.

Connects to the running FastAPI env server and runs a full 4-stage episode per task:

  Stage 1 – select_po       : LLM picks the matching PO candidate.
  Stage 2 – compare_items   : LLM evaluates each invoice line item vs PO & GRN.
  Stage 3 – flag_discrepancies: LLM flags each discrepancy it found.
  Stage 4 – final_decision  : LLM issues the definitive approve/flag/reject.

STDOUT FORMAT (strict – only these three line types):
    [START] task=<id> env=<benchmark> model=<model>
    [STEP]  step=<n> action=<json> reward=<r> done=<bool> info=<json>
    [END]   success=<bool> steps=<n> rewards=<csv>

All debug output goes to stderr.

Required environment variables (see .env):
    API_BASE_URL  – FastAPI server base URL  (hackathon standard)
    ENV_BASE_URL  – FastAPI server base URL  (legacy alias, fallback)
    MODEL_NAME    – model identifier          (hackathon standard)
    LLM_MODEL     – model identifier          (legacy alias, fallback)
    HF_TOKEN      – API key / HuggingFace token (hackathon standard)
    LLM_API_KEY   – API key                  (legacy alias, fallback)
    LLM_PROVIDER  – "together" | "groq" | "openai"  (default: together)

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

# Environment (FastAPI) server URL — where /reset, /step, /state live
# Default port MUST match Dockerfile EXPOSE port (7860)
ENV_SERVER_URL = (
    os.getenv("ENV_BASE_URL")
    or "http://localhost:7860"
)

# --- MANDATORY HACKATHON VARIABLES (PHASE 2) ---
# Judges inject API_BASE_URL (LiteLLM proxy) + HF_TOKEN (key) + MODEL_NAME
LLM_BASE_URL = (
    os.getenv("API_BASE_URL")
    or "https://router.huggingface.co/v1"
)
LLM_MODEL = (
    os.getenv("MODEL_NAME")
    or os.getenv("LLM_MODEL")
    or "meta-llama/Llama-3.3-70B-Instruct-Turbo"
)
LLM_API_KEY = (
    os.getenv("API_KEY")        # Phase 2: judges inject this exact variable name
    or os.getenv("HF_TOKEN")    # local testing fallback
    or os.getenv("LLM_API_KEY") # legacy fallback
    or "placeholder"
)

BENCHMARK         = "InvoiceReconciliationBenchmark-v1"
SUCCESS_THRESHOLD = 0.6   # cumulative reward >= this → success

ALL_TASKS: List[str] = [
    "easy-exact-match",
    "medium-fuzzy-match",
    "hard-discrepancy-detection",
    "ambiguous-split-invoice",
]

VALID_DISCREPANCY_TYPES = {
    "price_mismatch", "quantity_mismatch", "vendor_name_mismatch",
    "po_not_found", "duplicate_invoice", "partial_delivery",
    "extra_charge", "missing_line_item",
}

VALID_FINAL_DECISIONS = {"approve", "flag_discrepancy", "reject"}

# ---------------------------------------------------------------------------
# Logging helpers  (ONLY these functions write to stdout)
# ---------------------------------------------------------------------------

def _bool_str(v: bool) -> str:
    return "true" if v else "false"


def log_start(task: str, model: str) -> None:
    print(f"[START] task={task} env={BENCHMARK} model={model}", flush=True)


def log_step(step: int, action: Dict[str, Any], reward: float,
             done: bool, error: Optional[str] = None) -> None:
    action_field = json.dumps(action, ensure_ascii=True, separators=(",", ":"))
    error_field  = error if error else "null"
    print(
        f"[STEP] step={step} action={action_field} "
        f"reward={reward:.2f} done={_bool_str(done)} error={error_field}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_csv = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={_bool_str(success)} steps={steps} rewards={rewards_csv}",
          flush=True)


def _dbg(msg: str) -> None:
    """Write debug line to stderr only – never stdout."""
    print(f"[dbg] {msg}", file=sys.stderr, flush=True)

# ---------------------------------------------------------------------------
# Environment HTTP client
# ---------------------------------------------------------------------------

def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    # Use ENV_SERVER_URL for the task/environment server
    resp = requests.post(f"{ENV_SERVER_URL}{path}", json=payload, timeout=30)
    if not resp.ok:
        _dbg(f"HTTP {resp.status_code} on {path}: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def env_reset(task_id: str) -> Dict[str, Any]:
    return _post("/reset", {"task_id": task_id})


def env_step(action: Dict[str, Any]) -> Dict[str, Any]:
    """Submit action wrapped in the expected {'action': {...}} envelope."""
    return _post("/step", {"action": action})

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        text  = "\n".join(inner).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}

# ---------------------------------------------------------------------------
# LLM call — MANDATORY: use OpenAI client routed through API_BASE_URL proxy
# ---------------------------------------------------------------------------

from openai import OpenAI as _OpenAI

def call_llm(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Call LLM via OpenAI-compatible client using API_BASE_URL + HF_TOKEN.

    Hackathon requirement: ALL LLM calls must use the OpenAI client with
    base_url=API_BASE_URL and api_key=HF_TOKEN so they route through
    the judges' LiteLLM proxy (Phase 2 validation).
    """
    try:
        client = _OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY or "placeholder",
        )
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=600,
        )
        return _extract_json(resp.choices[0].message.content or "")
    except Exception as exc:
        _dbg(f"[warn] LLM call failed: {exc}")
        return {}

# ---------------------------------------------------------------------------
# Stage-specific prompt builders & action constructors
# ---------------------------------------------------------------------------

# ── Stage 1: Select PO ───────────────────────────────────────────────────

_SELECT_PO_SYSTEM = """
You are an expert Accounts-Payable reconciliation agent.

You will receive a JSON object with:
  - invoice       : the invoice to be reconciled
  - available_pos : a list of Purchase Order candidates

Your task is to select the PO that best matches the invoice (by vendor name,
line items, and po_reference if available).

Respond with ONLY valid JSON — no markdown, no prose:
{
  "action_type": "select_po",
  "po_id":       "<exact po_id string from available_pos>",
  "reasoning":   "<brief reason>"
}
""".strip()


def _build_select_po_prompt(obs: Dict[str, Any]) -> str:
    return json.dumps({
        "invoice":       obs.get("invoice"),
        "available_pos": obs.get("available_pos", []),
        "feedback":      obs.get("feedback", ""),
    }, default=str, indent=2)


def _make_select_po_action(obs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw = call_llm([
            {"role": "system", "content": _SELECT_PO_SYSTEM},
            {"role": "user",   "content": _build_select_po_prompt(obs)},
        ])
    except Exception as e:
        _dbg(f"select_po LLM failed ({e}), using fallback")
        raw = {}
    _dbg(f"select_po LLM raw: {raw}")

    po_id = str(raw.get("po_id") or "").strip()
    # Fallback: pick the PO whose vendor most closely matches invoice vendor
    if not po_id:
        inv_vendor = (obs.get("invoice") or {}).get("vendor_name", "").lower()
        for po in (obs.get("available_pos") or []):
            if po.get("vendor_name", "").lower()[:4] == inv_vendor[:4]:
                po_id = po["po_id"]
                break
    if not po_id and obs.get("available_pos"):
        po_id = obs["available_pos"][0]["po_id"]

    return {
        "action_type": "select_po",
        "po_id":       po_id,
        "reasoning":   str(raw.get("reasoning") or "")[:300],
    }


# ── Stage 2: Compare Items ────────────────────────────────────────────────

_COMPARE_ITEM_SYSTEM = """
You are an expert Accounts-Payable reconciliation agent.

You receive:
  - invoice_item    : one invoice line item (description, quantity, unit_price)
  - po_line_items   : all line items from the selected Purchase Order
  - grn_items       : all items in the Goods Received Note (quantities actually received)

Determine for this invoice item:
  1. found_in_po      – does it have a matching entry in po_line_items? (bool)
  2. price_matches    – does the invoice unit_price equal the PO unit_price? (bool, true if not found in PO)
  3. quantity_matches – does the invoice quantity equal the GRN quantity_received? (bool, true if not in GRN)

Matching is fuzzy: look for shared words in description.

Respond with ONLY valid JSON — no markdown:
{
  "action_type":          "compare_item",
  "invoice_item_index":   <integer>,
  "po_item_description":  "<best PO item description or empty string>",
  "found_in_po":          <true|false>,
  "price_matches":        <true|false>,
  "quantity_matches":     <true|false>
}
""".strip()


def _build_compare_item_prompt(
    item_index: int,
    inv_item: Dict[str, Any],
    po_items: List[Dict[str, Any]],
    grn_items: List[Dict[str, Any]],
) -> str:
    return json.dumps({
        "invoice_item_index": item_index,
        "invoice_item":       inv_item,
        "po_line_items":      po_items,
        "grn_items":          grn_items,
    }, default=str, indent=2)


def _make_compare_item_action(
    item_index: int,
    inv_item: Dict[str, Any],
    obs: Dict[str, Any],
) -> Dict[str, Any]:
    selected_po = obs.get("selected_po") or {}
    po_items    = selected_po.get("line_items", [])
    grn_items   = (obs.get("goods_received_note") or {}).get("items_received", [])

    try:
        raw = call_llm([
            {"role": "system", "content": _COMPARE_ITEM_SYSTEM},
            {"role": "user",   "content": _build_compare_item_prompt(
                item_index, inv_item, po_items, grn_items
            )},
        ])
    except Exception as e:
        _dbg(f"compare_item[{item_index}] LLM failed ({e}), using fallback")
        raw = {}
    _dbg(f"compare_item[{item_index}] LLM raw: {raw}")

    return {
        "action_type":          "compare_item",
        "invoice_item_index":   item_index,
        "po_item_description":  str(raw.get("po_item_description") or ""),
        "found_in_po":          bool(raw.get("found_in_po", True)),
        "price_matches":        bool(raw.get("price_matches", True)),
        "quantity_matches":     bool(raw.get("quantity_matches", True)),
    }


# ── Stage 3: Flag Discrepancies ───────────────────────────────────────────

_FLAG_DISCREPANCY_SYSTEM = """
You are an expert Accounts-Payable reconciliation agent.

Based on the comparison results provided, identify ALL discrepancies and list them.

For EACH discrepancy you must output ONE JSON object (call this tool once per discrepancy):
{
  "action_type":      "flag_discrepancy",
  "discrepancy_type": "<one of: price_mismatch | quantity_mismatch | vendor_name_mismatch | po_not_found | duplicate_invoice | partial_delivery | extra_charge | missing_line_item>",
  "details":          "<concise description with specific values>"
}

If there are MULTIPLE discrepancies, output a JSON array of such objects:
[
  { "action_type": "flag_discrepancy", "discrepancy_type": "price_mismatch", "details": "..." },
  { "action_type": "flag_discrepancy", "discrepancy_type": "quantity_mismatch", "details": "..." }
]

If there are NO discrepancies, output an empty array: []
""".strip()


def _build_flag_discrepancy_prompt(obs: Dict[str, Any]) -> str:
    return json.dumps({
        "invoice":            obs.get("invoice"),
        "selected_po":        obs.get("selected_po"),
        "goods_received_note": obs.get("goods_received_note"),
        "comparison_results": obs.get("comparison_results", []),
        "feedback":           obs.get("feedback", ""),
    }, default=str, indent=2)


def _make_flag_discrepancy_actions(obs: Dict[str, Any]) -> List[Dict[str, Any]]:
    messages = [
        {"role": "system", "content": _FLAG_DISCREPANCY_SYSTEM},
        {"role": "user",   "content": _build_flag_discrepancy_prompt(obs)},
    ]

    # Use OpenAI client (routed through API_BASE_URL proxy) for raw text output
    raw_text = ""
    try:
        client = _OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY or "placeholder",
        )
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=800,
        )
        raw_text = resp.choices[0].message.content or ""
        if raw_text:
            _dbg("flag_discrepancy: LLM call succeeded via OpenAI proxy")
    except Exception as exc:
        _dbg(f"[warn] flag_discrepancy LLM call failed: {exc}")
        return []  # safe fallback — no flags, episode continues to Stage 4

    raw_text = raw_text.strip()
    _dbg(f"flag_discrepancy LLM raw text: {raw_text[:400]}")

    # Strip markdown fences
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        raw_text = "\n".join(inner).strip()

    # Parse: could be array or single object
    parsed: Any = None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", raw_text, flags=re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    if parsed is None:
        _dbg("flag_discrepancy: could not parse LLM output, returning []")
        return []

    if isinstance(parsed, dict):
        parsed = [parsed]
    elif not isinstance(parsed, list):
        return []

    actions = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        dtype = str(item.get("discrepancy_type") or "").strip().lower()
        if dtype not in VALID_DISCREPANCY_TYPES:
            _dbg(f"  skipping unknown discrepancy_type: {dtype!r}")
            continue
        actions.append({
            "action_type":      "flag_discrepancy",
            "discrepancy_type": dtype,
            "details":          str(item.get("details") or "")[:400],
        })

    return actions


# ── Stage 4: Final Decision ───────────────────────────────────────────────

_FINAL_DECISION_SYSTEM = """
You are an expert Accounts-Payable reconciliation agent making the FINAL decision.

Review the complete reconciliation state and issue the definitive verdict.

Decision rules:
  "approve"          — ALL prices, quantities, vendor name match perfectly. No extras.
  "flag_discrepancy" — Minor issues only: small price delta (≤$5) OR fuzzy vendor name mismatch ONLY.
  "reject"           — Serious issues: large price overcharge (>$5), quantity invoiced > received,
                       extra line items not in PO, or MULTIPLE simultaneous discrepancies.

Respond with ONLY valid JSON — no markdown, no prose:
{
  "action_type":       "final_decision",
  "decision":          "<approve|flag_discrepancy|reject>",
  "matched_po_id":     "<po_id string>",
  "discrepancy_flags": ["<discrepancy_type>", ...],
  "reasoning":         "<concise explanation citing specific values>"
}
""".strip()


def _build_final_decision_prompt(obs: Dict[str, Any]) -> str:
    return json.dumps({
        "invoice":              obs.get("invoice"),
        "selected_po":         obs.get("selected_po"),
        "goods_received_note": obs.get("goods_received_note"),
        "comparison_results":  obs.get("comparison_results", []),
        "flagged_discrepancies": obs.get("flagged_discrepancies", []),
        "feedback":            obs.get("feedback", ""),
    }, default=str, indent=2)


def _make_final_decision_action(obs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        raw = call_llm([
            {"role": "system", "content": _FINAL_DECISION_SYSTEM},
            {"role": "user",   "content": _build_final_decision_prompt(obs)},
        ])
    except Exception as e:
        _dbg(f"final_decision LLM failed ({e}), using fallback")
        raw = {}
    _dbg(f"final_decision LLM raw: {raw}")

    decision = str(raw.get("decision") or "flag_discrepancy").strip().lower()
    if decision not in VALID_FINAL_DECISIONS:
        decision = "flag_discrepancy"

    po_id = str(raw.get("matched_po_id") or "").strip()
    if not po_id and obs.get("selected_po"):
        po_id = (obs["selected_po"] or {}).get("po_id", "")

    flags = [
        f.strip().lower()
        for f in (raw.get("discrepancy_flags") or [])
        if isinstance(f, str) and f.strip().lower() in VALID_DISCREPANCY_TYPES
    ]

    return {
        "action_type":       "final_decision",
        "decision":          decision,
        "matched_po_id":     po_id,
        "discrepancy_flags": flags,
        "reasoning":         str(raw.get("reasoning") or "")[:500],
    }


# ---------------------------------------------------------------------------
# Single task runner (multi-step)
# ---------------------------------------------------------------------------

def run_task(task_id: str) -> Dict[str, Any]:
    """Run a complete multi-step episode and return summary info."""
    rewards:    List[float] = []
    step_count: int = 0
    success:    bool = False
    final_info: Dict[str, Any] = {}

    log_start(task=task_id, model=LLM_MODEL)

    try:
        # ── 1. Reset ──────────────────────────────────────────────────────
        obs = env_reset(task_id)
        _dbg(f"episode_id={obs.get('episode_id')}  task={task_id}  stage={obs.get('stage')}")

        # ── 2. Stage 1 – Select PO ────────────────────────────────────────
        action = _make_select_po_action(obs)
        obs    = env_step(action)
        step_count += 1
        reward = float(obs.get("reward", 0.0))
        done   = bool(obs.get("is_done", False))
        rewards.append(reward)
        log_step(step=step_count, action=action, reward=reward, done=done,
                 error=None)
        _dbg(f"  stage={obs.get('stage')}  cumulative={obs.get('cumulative_reward')}"
             f"  feedback: {obs.get('feedback','')[:80]}")

        # ── 3. Stage 2 – Compare Items (one step per line item) ───────────
        invoice_items = (obs.get("invoice") or {}).get("line_items", [])
        compared_indices: set = set()
        # Iterate until all items compared or stage advances
        for idx, inv_item in enumerate(invoice_items):
            if idx in compared_indices:
                continue
            action = _make_compare_item_action(idx, inv_item, obs)
            obs    = env_step(action)
            step_count += 1
            reward = float(obs.get("reward", 0.0))
            done   = bool(obs.get("is_done", False))
            rewards.append(reward)
            log_step(step=step_count, action=action, reward=reward, done=done,
                     error=None)
            _dbg(f"  compare[{idx}]  stage={obs.get('stage')}  "
                 f"feedback: {obs.get('feedback','')[:80]}")
            compared_indices.add(idx)

        # ── 4. Stage 3 – Flag Discrepancies ───────────────────────────────
        flag_actions = _make_flag_discrepancy_actions(obs)
        _dbg(f"  flagging {len(flag_actions)} discrepancy(ies)")

        if flag_actions:
            for flag_action in flag_actions:
                obs    = env_step(flag_action)
                step_count += 1
                reward = float(obs.get("reward", 0.0))
                done   = bool(obs.get("is_done", False))
                rewards.append(reward)
                log_step(step=step_count, action=flag_action, reward=reward, done=done,
                         error=None)
                _dbg(f"  flagged {flag_action['discrepancy_type']}"
                     f"  feedback: {obs.get('feedback','')[:80]}")
        else:
            _dbg("  no discrepancies flagged in stage 3")

        # ── 5. Stage 4 – Final Decision ───────────────────────────────────
        action = _make_final_decision_action(obs)
        obs    = env_step(action)
        step_count += 1
        reward = float(obs.get("reward", 0.0))
        done   = bool(obs.get("is_done", True))
        rewards.append(reward)
        log_step(step=step_count, action=action, reward=reward, done=done,
                 error=None)
        _dbg(f"  final stage={obs.get('stage')}  done={done}  "
             f"cumulative={obs.get('cumulative_reward')}")

        # ── Episode outcome ───────────────────────────────────────────────
        cumulative = float(obs.get("cumulative_reward", sum(rewards)))
        success    = cumulative >= SUCCESS_THRESHOLD
        final_info = obs.get("info", {})
        final_info["cumulative_reward"] = cumulative

    except requests.exceptions.ConnectionError as conn_err:
        _dbg(f"[ERROR] Cannot reach env server at {ENV_SERVER_URL}: {conn_err}")
        _dbg("Set ENV_BASE_URL to the correct server URL.")
        # Still make one LLM call so the proxy key is registered
        try:
            call_llm([{"role": "user", "content": "ping"}])
        except Exception:
            pass
    except Exception as exc:
        _dbg(f"[ERROR] Unexpected error in task '{task_id}': {exc}")
        import traceback
        traceback.print_exc(file=sys.stderr)

    log_end(success=success, steps=step_count, score=final_info.get("cumulative_reward", 0.0), rewards=rewards)
    return final_info


# ---------------------------------------------------------------------------
# Multi-task runner
# ---------------------------------------------------------------------------

def run_all_tasks() -> None:
    results: List[Dict[str, Any]] = []
    for task_id in ALL_TASKS:
        info = run_task(task_id)
        results.append({"task_id": task_id, **info})

    # Summary goes to stderr to avoid polluting stdout
    print("\n" + "=" * 60, file=sys.stderr)
    print("  SUMMARY", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    total = 0.0
    for r in results:
        cr = r.get("cumulative_reward", 0.0)
        total += cr
        icon = "[PASS]" if cr >= SUCCESS_THRESHOLD else "[FAIL]"
        print(f"  {icon}  {r['task_id']:<35s}  cumulative={cr:.4f}  "
              f"decision={r.get('submitted_decision','?')}"
              f"  correct={r.get('decision_correct','?')}",
              file=sys.stderr)
    n = len(results)
    print(f"\n  Avg cumulative: {total/n if n else 0:.4f}  "
          f"Passed: {sum(1 for r in results if r.get('cumulative_reward',0) >= SUCCESS_THRESHOLD)}/{n}",
          file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Invoice Reconciliation multi-step inference script"
    )
    parser.add_argument(
        "--task",
        default="all",
        help="Task to run. Use 'all' or one of: " + ", ".join(ALL_TASKS),
    )
    parser.add_argument("--base-url", default=None, help="Override ENV_BASE_URL")
    parser.add_argument("--provider", default=None,
                        choices=["together", "groq", "openai"],
                        help="Override LLM_PROVIDER")
    parser.add_argument("--model", default=None, help="Override LLM_MODEL")
    args = parser.parse_args()

    global ENV_SERVER_URL, LLM_BASE_URL, LLM_MODEL
    if args.base_url: ENV_SERVER_URL = args.base_url
    if args.model:    LLM_MODEL    = args.model

    if not LLM_API_KEY:
        print("[warn] LLM_API_KEY is not set — set it in .env or the environment.",
              file=sys.stderr, flush=True)

    if args.task == "all":
        run_all_tasks()
    else:
        run_task(args.task)


if __name__ == "__main__":
    main()
