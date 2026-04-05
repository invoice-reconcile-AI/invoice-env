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

# Optional: Mount frontend folder for static assets (images, CSS, JS) if needed
# Use a path relative to the root where the server is typically started
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


class ResetRequest(BaseModel):
    task_id: str = "easy-exact-match"  # default so empty body doesn't 422


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


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


@app.get("/tasks")
def list_tasks() -> JSONResponse:
    """List all available task IDs with difficulty metadata."""
    return JSONResponse(
        content={
            "tasks": [
                {
                    "task_id": tid,
                    "description": scenario["description"],
                    "expected_final_action": scenario["expected_final_action"],
                    "expected_discrepancies": [
                        d.value for d in scenario["expected_discrepancies"]
                    ],
                }
                for tid, scenario in _SCENARIOS.items()
            ]
        }
    )

@app.get("/web", response_class=FileResponse)
@app.get("/", response_class=FileResponse)
def serve_ui():
    """Serves the interactive UI dashboard."""
    ui_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(ui_path):
        return FileResponse(ui_path)
    raise HTTPException(status_code=404, detail="UI file not found. Ensure frontend/index.html exists.")
