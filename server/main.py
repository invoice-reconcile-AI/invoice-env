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
    <title>Luminix Invoice Arena</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d1117;
            --card: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --accent: #58a6ff;
            --success: #3fb950;
        }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 40px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            max-width: 900px;
            width: 100%;
        }
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        h1 {
            font-size: 2.5rem;
            color: var(--accent);
            margin-bottom: 10px;
        }
        .badge {
            background-color: var(--success);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 40px;
        }
        .card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            transition: transform 0.2s;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .card h3 {
            margin-top: 0;
            color: var(--accent);
            font-family: 'JetBrains Mono', monospace;
        }
        code {
            font-family: 'JetBrains Mono', monospace;
            background: #1f2428;
            padding: 2px 6px;
            border-radius: 4px;
            color: #ff7b72;
        }
        .footer {
            margin-top: 60px;
            text-align: center;
            font-size: 0.9rem;
            color: #8b949e;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="badge">OPENENV COMPLIANT v0.3.2</span>
            <h1>Luminix Invoice Arena</h1>
            <p>High-fidelity AI agent evaluation for complex back-office workflows.</p>
        </div>

        <div class="grid">
            <div class="card">
                <h3>54 SCENARIOS</h3>
                <p>Varied difficulty levels from exact-match to multi-currency compliance frauds.</p>
            </div>
            <div class="card">
                <h3>4-STAGE PROTOCOL</h3>
                <p>Enforced sequence: Select PO → Compare → Flag → Decision. Zero shortcuts allowed.</p>
            </div>
            <div class="card">
                <h3>SCORE CAPPING</h3>
                <p>Strict 0.99 normalized score ceiling as per Meta Hackathon Phase 2 standards.</p>
            </div>
        </div>

        <div style="margin-top: 40px; background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px;">
            <h3 style="color: var(--accent); margin-top:0;">QUICK START</h3>
            <pre style="background: #000; padding: 15px; border-radius: 8px; overflow-x: auto; color: #d1d5da;"><code>curl -X POST https://{{host}}/reset \
-H "Content-Type: application/json" \
-d '{"task_id": "easy-exact-match"}'</code></pre>
        </div>

        <div class="footer">
            Built for Meta Hackathon 2026 | Powered by OpenEnv
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
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
