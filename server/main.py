"""FastAPI application exposing the OpenEnv Invoice Reconciliation environment."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.env import env
from server.models import InvoiceAction, InvoiceObservation

app = FastAPI(
    title="Invoice Reconciliation OpenEnv",
    description=(
        "An OpenEnv-compatible reinforcement-learning environment for automated "
        "invoice-to-payment reconciliation. Supports 3 difficulty tiers: "
        "easy-exact-match, medium-fuzzy-match, and hard-discrepancy-detection."
    ),
    version="1.0.0",
)


class ResetRequest(BaseModel):
    task_id: str


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/reset", response_model=InvoiceObservation)
def reset(request: ResetRequest) -> InvoiceObservation:
    """Start a new episode for the given task_id."""
    try:
        return env.reset(request.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/step", response_model=InvoiceObservation)
def step(action: InvoiceAction) -> InvoiceObservation:
    """Submit an action and receive the next observation."""
    try:
        return env.step(action)
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
    """List all available task IDs."""
    from server.env import _SCENARIOS  # noqa: PLC0415

    return JSONResponse(
        content={
            "tasks": [
                {"task_id": tid, "description": scenario["description"]}
                for tid, scenario in _SCENARIOS.items()
            ]
        }
    )
