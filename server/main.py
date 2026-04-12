"""FastAPI application exposing the OpenEnv Invoice Reconciliation environment."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

from server.env import _SCENARIOS, env
from server.models import InvoiceActionWrapper, InvoiceObservation

app = FastAPI(
    title="Invoice Reconciliation OpenEnv",
    description=(
        "A multi-step OpenEnv-compatible RL environment for automated "
        "invoice-to-payment reconciliation. Supports 3 difficulty tiers: "
        "easy-exact-match, medium-fuzzy-match, hard-discrepancy-detection. "
        "\n\nEpisode stages: select_po → compare_items → flag_discrepancies → final_decision."
    ),
    version="2.0.0",
)

# Mounting static files from the frontend folder
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Serving the UI at the root route
@app.get("/", response_class=HTMLResponse)
@app.get("/web", response_class=HTMLResponse)
async def serve_ui():
    return """
    <h1>Luminix Invoice Environment - API Live</h1>
    <p>Backend ready for OpenEnv evaluation.</p>
    <p>Test endpoint: <code>POST /reset</code></p>
    <p>Docs: <a href="/docs">/docs</a></p>
    """


class ResetRequest(BaseModel):
    task_id: str = "easy-exact-match"  # default so empty body doesn't 422


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/tasks")
async def get_tasks():
    return {
        "tasks": list(_SCENARIOS.keys()),
        "total": len(_SCENARIOS),
        "curriculum": {
            "easy": ["easy-exact-match"],
            "medium": ["medium-fuzzy-match", "multi-currency-compliance", "vat-reverse-charge"],
            "hard": ["hard-discrepancy-detection", "ambiguous-split-invoice", "compliance-soc2-vendor", "duplicate-invoice-detection"],
            "expert": ["partial-delivery-po", "vendor-sanctions-check"]
        },
        "compliance_rules": list(set([s.get("compliance_rule") for s in _SCENARIOS.values() if s.get("compliance_rule")]))
    }


@app.post("/reset", response_model=InvoiceObservation)
def reset(request: ResetRequest = None) -> InvoiceObservation:
    """Start a new episode for the given task_id.

    Accepts an optional JSON body: {"task_id": "easy-exact-match"}
    If no body is sent (or empty body), defaults to 'easy-exact-match'.
    """
    if request is None:
        request = ResetRequest()
    try:
        return env.reset(request.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/step", response_model=InvoiceObservation)
def step(payload: InvoiceActionWrapper) -> InvoiceObservation:
    """Submit a stage-appropriate action and receive the next observation.

    The request body must be:

    ```json
    {
      "action": {
        "action_type": "select_po",
        "po_id": "PO-5001"
      }
    }
    ```

    Where ``action_type`` is one of:
    - ``"select_po"``       → Stage 1
    - ``"compare_item"``    → Stage 2  (repeat for each invoice line item)
    - ``"flag_discrepancy"``→ Stage 3  (repeat for each discrepancy found)
    - ``"final_decision"``  → Stage 4  (terminates episode, ``is_done=true``)
    """
    try:
        return env.step(payload.action)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/state", response_model=InvoiceObservation)
def state() -> InvoiceObservation:
    """Return the current observation without advancing the episode."""
    try:
        return env.state()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



