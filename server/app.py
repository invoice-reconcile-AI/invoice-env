"""FastAPI app wiring for Invoice Reconciliation environment."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Body, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError

try:
    from openenv.core.env_server import create_app
    from openenv.core.env_server.http_server import StepRequest
except ImportError:
    from openenv_core.env_server import create_app
    from openenv_core.env_server.http_server import StepRequest

try:
    from ..models import InvoiceReconciliationAction, InvoiceReconciliationObservation
    from .environment import InvoiceReconciliationEnvironment
except ImportError:
    from models import InvoiceReconciliationAction, InvoiceReconciliationObservation
    from server.environment import InvoiceReconciliationEnvironment


app = create_app(
    InvoiceReconciliationEnvironment,
    InvoiceReconciliationAction,
    InvoiceReconciliationObservation,
    env_name="invoice_reconciliation_env",
    max_concurrent_envs=8,
)


def _normalize_step_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "action" in payload:
        return payload

    action_keys = {"po_id", "decision", "note"}
    if not any(key in payload for key in action_keys):
        return payload

    action_payload = {key: payload[key] for key in action_keys if key in payload}
    passthrough = {
        key: value for key, value in payload.items() if key not in action_keys
    }
    passthrough["action"] = action_payload
    return passthrough


def _install_step_compat_route() -> None:
    """Replace /step with a compatibility handler that accepts bare payloads."""
    original_step_endpoint = None

    for route in list(app.router.routes):
        if (
            isinstance(route, APIRoute)
            and route.path == "/step"
            and "POST" in route.methods
        ):
            original_step_endpoint = route.endpoint
            app.router.routes.remove(route)
            break

    if original_step_endpoint is None:
        return

    @app.post("/step")
    async def step_compat(payload: dict[str, Any] = Body(default_factory=dict)):
        normalized = _normalize_step_payload(payload)
        try:
            request_model = StepRequest.model_validate(normalized)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.errors(),
            ) from exc

        return await original_step_endpoint(request_model)

    app.openapi_schema = None


_install_step_compat_route()


@app.middleware("http")
async def normalize_step_payload(request: Request, call_next):
    """Accept bare /step action payloads by wrapping into {'action': ...}."""
    path = request.url.path.rstrip("/") or "/"
    if request.method == "POST" and path.endswith("/step"):
        raw_body = await request.body()
        if raw_body:
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                payload = None

            if isinstance(payload, dict):
                normalized = _normalize_step_payload(payload)
                if normalized is not payload:
                    rewritten_body = json.dumps(normalized).encode("utf-8")

                    async def receive() -> dict[str, Any]:
                        return {
                            "type": "http.request",
                            "body": rewritten_body,
                            "more_body": False,
                        }

                    request._receive = receive
                    request._body = rewritten_body

    return await call_next(request)


def _has_post_route(path: str) -> bool:
    for route in app.routes:
        route_path = getattr(route, "path", None)
        route_methods = getattr(route, "methods", set())
        if route_path == path and "POST" in route_methods:
            return True
    return False


if not _has_post_route("/mcp"):

    @app.post("/mcp")
    async def mcp_fallback(
        payload: dict[str, Any] = Body(default_factory=dict),
    ) -> JSONResponse:
        """Compatibility MCP endpoint for OpenEnv runtimes lacking native /mcp."""
        request_id = payload.get("id")
        method = payload.get("method")

        if method == "tools/list":
            result = {"tools": []}
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "serverInfo": {
                    "name": "invoice_reconciliation_env",
                    "version": "1.0.0",
                },
            }
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

        error = {
            "code": -32601,
            "message": "Method not found",
        }
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": error})


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
