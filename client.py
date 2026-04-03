"""WebSocket client for the Invoice Reconciliation OpenEnv server."""

from __future__ import annotations

from typing import Dict

try:
    from openenv.core.client_types import StepResult
    from openenv.core.env_client import EnvClient
except ImportError:
    from openenv_core.client_types import StepResult
    from openenv_core.env_client import EnvClient

try:
    from .models import (
        InvoiceReconciliationAction,
        InvoiceReconciliationObservation,
        InvoiceReconciliationState,
    )
except ImportError:
    from models import (
        InvoiceReconciliationAction,
        InvoiceReconciliationObservation,
        InvoiceReconciliationState,
    )


class InvoiceReconciliationEnv(
    EnvClient[
        InvoiceReconciliationAction,
        InvoiceReconciliationObservation,
        InvoiceReconciliationState,
    ]
):
    """Typed client for the Invoice Reconciliation environment."""

    def _step_payload(self, action: InvoiceReconciliationAction) -> Dict:
        return {
            "po_id": action.po_id,
            "decision": action.decision,
            "note": action.note,
        }

    def _parse_result(
        self, payload: Dict
    ) -> StepResult[InvoiceReconciliationObservation]:
        obs_data = payload.get("observation", {})
        parsed_obs = InvoiceReconciliationObservation.model_validate(
            {
                **obs_data,
                "done": payload.get("done", obs_data.get("done", False)),
                "reward": payload.get("reward", obs_data.get("reward", 0.0)),
            }
        )

        return StepResult(
            observation=parsed_obs,
            reward=payload.get("reward", 0.0),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> InvoiceReconciliationState:
        return InvoiceReconciliationState.model_validate(payload)
