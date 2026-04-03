"""Baseline inference script for Invoice Reconciliation OpenEnv tasks.

This script emits only the mandatory stdout line formats:
  [START] ...
  [STEP]  ...
  [END]   ...
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Dict, List

from client import InvoiceReconciliationEnv
from models import InvoiceReconciliationAction
from openai import OpenAI

API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
HF_TOKEN = os.getenv("HF_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_KEY = os.getenv("API_KEY")
AUTH_TOKEN = HF_TOKEN or OPENAI_API_KEY or API_KEY
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
ENV_BASE_URL = os.getenv("ENV_BASE_URL") or "http://localhost:8000"

BENCHMARK = "invoice_reconciliation"
TASKS = [
    "easy-exact-match",
    "medium-fuzzy-tolerance",
    "hard-discrepancy-detection",
]
MAX_STEPS = 2
TEMPERATURE = 0.0
MAX_TOKENS = 250


SYSTEM_PROMPT = (
    "You are an accounts-payable reconciliation agent. "
    "Return EXACTLY one JSON object with keys po_id, decision, note. "
    "decision must be one of: pay, hold, flag. "
    "Do not add markdown, prose, or extra keys."
)


def _bool(v: bool) -> str:
    return "true" if v else "false"


def _sanitize_error(message: str) -> str:
    return " ".join(message.strip().split())


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _normalize_action_payload(raw: Dict[str, Any], fallback_po_id: str) -> Dict[str, str]:
    po_id = str(raw.get("po_id") or fallback_po_id)
    decision = str(raw.get("decision") or "hold").strip().lower()
    note = str(raw.get("note") or "")

    if decision not in {"pay", "hold", "flag"}:
        decision = "hold"

    if len(note) > 400:
        note = note[:400]

    return {
        "po_id": po_id,
        "decision": decision,
        "note": note,
    }


def _connect_env_sync():
    if LOCAL_IMAGE_NAME:
        async_client = asyncio.run(
            InvoiceReconciliationEnv.from_docker_image(LOCAL_IMAGE_NAME)
        )
        return async_client.sync()
    return InvoiceReconciliationEnv(base_url=ENV_BASE_URL).sync()


def _build_user_prompt(observation) -> str:
    po_view = [
        {
            "po_id": po.po_id,
            "vendor_name": po.vendor_name,
            "total_amount": po.total_amount,
            "currency": po.currency,
            "line_count": len(po.lines),
        }
        for po in observation.candidate_pos
    ]

    grn_view = [
        {
            "po_id": entry.po_id,
            "sku": entry.sku,
            "received_qty": entry.received_qty,
        }
        for entry in observation.grn_log
    ]

    payload = {
        "task_id": observation.task_id,
        "difficulty": observation.difficulty,
        "stage": observation.stage,
        "invoice_text": observation.invoice_text,
        "candidate_pos": po_view,
        "grn_log": grn_view,
        "hints": observation.hints,
        "allowed_decisions": observation.allowed_decisions,
    }
    return json.dumps(payload, ensure_ascii=True)


def _choose_action(client: OpenAI, observation) -> InvoiceReconciliationAction:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(observation)},
        ],
    )

    text = response.choices[0].message.content or ""
    data = _extract_json_object(text)

    fallback_po_id = (
        observation.candidate_pos[0].po_id if observation.candidate_pos else "UNKNOWN-PO"
    )
    if not data:
        data = {
            "po_id": fallback_po_id,
            "decision": "hold",
            "note": "Could not parse model response as JSON.",
        }

    normalized = _normalize_action_payload(data, fallback_po_id)
    return InvoiceReconciliationAction.model_validate(normalized)


def run_task(client: OpenAI, task_name: str) -> None:
    rewards: List[float] = []
    success = False
    step_count = 0

    print(f"[START] task={task_name} env={BENCHMARK} model={MODEL_NAME}")

    try:
        with _connect_env_sync() as env:
            result = env.reset(task_id=task_name)

            while not result.done and step_count < MAX_STEPS:
                action = _choose_action(client, result.observation)
                result = env.step(action)

                step_count += 1
                reward = float(result.reward or 0.0)
                rewards.append(reward)

                raw_error = (result.observation.metadata or {}).get("last_action_error")
                error_field = (
                    "null" if not raw_error else _sanitize_error(str(raw_error))
                )
                action_for_log = {
                    "po_id": action.po_id,
                    "decision": str(action.decision.value),
                    "note": action.note,
                }
                action_field = json.dumps(
                    action_for_log,
                    ensure_ascii=True,
                    separators=(",", ":"),
                )

                print(
                    "[STEP] "
                    f"step={step_count} "
                    f"action={action_field} "
                    f"reward={reward:.2f} "
                    f"done={_bool(bool(result.done))} "
                    f"error={error_field}"
                )

            final_score = float(
                (result.observation.metadata or {}).get(
                    "final_score", result.observation.accumulated_score
                )
            )
            success = bool(result.done and final_score >= 0.8)

    except Exception:
        success = False

    rewards_csv = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={_bool(success)} steps={step_count} rewards={rewards_csv}")


def main() -> None:
    if not AUTH_TOKEN:
        raise SystemExit("Set one of HF_TOKEN, OPENAI_API_KEY, or API_KEY.")

    client = OpenAI(base_url=API_BASE_URL, api_key=AUTH_TOKEN)
    for task in TASKS:
        run_task(client, task)


if __name__ == "__main__":
    main()
