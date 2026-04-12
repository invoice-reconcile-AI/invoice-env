from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any
from .env import InvoiceReconciliationEnv
import uuid

app = FastAPI(
    title="Luminix Invoice Arena",
    description="High-fidelity agentic environment for multi-stage invoice reconciliation.",
    version="3.0.0"
)

# Global environment instance
env = InvoiceReconciliationEnv()
episodes = {}

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Luminix AI Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { margin: 0; font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 260px; background: #020617; border-right: 1px solid #1e293b; padding: 24px; display: flex; flex-direction: column; }
        .main { flex: 1; overflow-y: auto; padding: 40px; }
        .stat-card { background: #1e293b; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
        .stat-val { font-size: 24px; font-weight: 700; color: #38bdf8; }
        .stat-label { font-size: 12px; color: #94a3b8; text-transform: uppercase; }
        h1 { color: #f8fafc; font-size: 28px; margin-bottom: 8px; }
        .badge { background: #0ea5e9; color: white; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; margin-bottom: 24px; }
        pre { background: #020617; padding: 16px; border-radius: 8px; color: #38bdf8; overflow-x: auto; }
        .endpoint { color: #10b981; font-weight: 600; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2 style="color: #38bdf8; margin-top: 0;">LUMINIX</h2>
        <div class="stat-card">
            <div class="stat-val">54</div>
            <div class="stat-label">Total Task Scenarios</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">0.99</div>
            <div class="stat-label">Max Compliance Score</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">4/4</div>
            <div class="stat-label">Security Stages Live</div>
        </div>
    </div>
    <div class="main">
        <span class="badge">OPENENV PHASE 2 COMPLIANT</span>
        <h1>Invoice Reconciliation Engine</h1>
        <p style="color: #94a3b8;">High-fidelity agentic environment for multi-stage financial audit evaluation.</p>
        
        <div class="card">
            <h3>Environment Protocol</h3>
            <p>Strict stage-gating enforced: <code>select_po</code> &rarr; <code>compare_items</code> &rarr; <code>flag_discrepancy</code> &rarr; <code>final_decision</code>. Anti-exploit penalty of -0.10 for out-of-order actions.</p>
        </div>

        <div class="card">
            <h3>API Documentation</h3>
            <p><span class="endpoint">POST /reset</span> - Initialize episode: <code>{"task_id": "easy-exact-match"}</code></p>
            <p><span class="endpoint">POST /step</span> - Submit agent action</p>
            <pre>curl -X POST https://{{host}}/reset \\
-H "Content-Type: application/json" \\
-d '{"task_id": "easy-exact-match"}'</pre>
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
@app.get("/web", response_class=HTMLResponse)
async def home(request: Request):
    return HTML_CONTENT.replace("{{host}}", request.headers.get("host", "localhost:7860"))

class ResetRequest(BaseModel):
    task_id: str = "easy-exact-match"

@app.post("/reset")
async def reset(req: ResetRequest):
    episode_id = str(uuid.uuid4())
    obs = env.reset(req.task_id)
    episodes[episode_id] = {"env": env, "task_id": req.task_id}
    return {
        "episode_id": episode_id,
        "task_id": req.task_id,
        "observation": obs,
        "stage": env.state.stage,
        "allowed_action_types": env.get_allowed_action_types()
    }

@app.post("/step")
async def step(episode_id: str, action: dict):
    # In a real environment, you'd look up the environment by episode_id
    # For this hackathon version, we use the singleton env for simplicity
    obs, reward, done, info = env.step(action)
    return {
        "observation": obs,
        "reward": reward,
        "done": done,
        "info": info,
        "stage": env.state.stage,
        "allowed_action_types": env.get_allowed_action_types()
    }

@app.get("/tasks")
async def tasks():
    from .tasks import _SCENARIOS
    return {"tasks": list(_SCENARIOS.keys())}

@app.get("/health")
async def health():
    return {"status": "healthy"}
