from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any
from .env import InvoiceReconciliationEnv
import uuid

app = FastAPI(
    title="Luminix Invoice Arena",
    version="3.0.0"
)

# Global environment instance
env = InvoiceReconciliationEnv()

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Luminix Invoice Arena</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19;
            --sidebar: #020617;
            --card: #1e293b;
            --accent: #38bdf8;
            --text: #f8fafc;
            --muted: #94a3b8;
            --border: #1e293b;
        }
        body { margin: 0; font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 280px; background: var(--sidebar); border-right: 1px solid var(--border); padding: 32px 24px; display: flex; flex-direction: column; }
        .main { flex: 1; overflow-y: auto; padding: 60px 80px; }
        
        .hero { margin-bottom: 48px; }
        .hero h1 { font-size: 42px; margin: 0 0 12px 0; background: linear-gradient(to right, #fff, #38bdf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .hero p { color: var(--muted); font-size: 18px; margin: 0; }
        
        .pill-row { display: flex; gap: 12px; margin-top: 24px; flex-wrap: wrap; }
        .pill { background: #1e293b; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500; border: 1px solid #334155; }
        
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 48px; }
        .stat-card { background: var(--card); border-radius: 12px; padding: 24px; text-align: center; border: 1px solid var(--border); }
        .stat-val { font-size: 32px; font-weight: 700; color: var(--accent); margin-bottom: 4px; }
        .stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }

        .section-title { font-size: 14px; text-transform: uppercase; color: var(--muted); letter-spacing: 2px; margin-bottom: 24px; font-weight: 600; }
        
        .task-list { margin-bottom: 48px; }
        .task-item { display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid var(--border); }
        .task-name { font-size: 18px; font-weight: 600; }
        .task-meta { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--muted); }
        .tag-easy { color: #10b981; } .tag-med { color: #f59e0b; } .tag-hard { color: #ef4444; }

        .reward-box { background: #020617; border-radius: 12px; padding: 32px; text-align: center; font-family: monospace; font-size: 20px; border: 1px solid var(--border); margin-bottom: 48px; }
        
        .endpoints-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
        .endpoint-card { background: var(--card); border-radius: 12px; padding: 20px; border: 1px solid var(--border); }
        .ep-verb { color: var(--accent); font-weight: 700; margin-right: 8px; }
        
        .audit-trail { background: #020617; border-radius: 12px; padding: 24px; font-family: monospace; font-size: 14px; border: 1px solid var(--border); }
        .audit-line { margin: 8px 0; display: flex; gap: 16px; }
        .audit-step { color: var(--muted); width: 80px; }
        .audit-reward { color: #10b981; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 40px;">
            <div style="width: 32px; height: 32px; background: var(--accent); border-radius: 8px;"></div>
            <span style="font-size: 20px; font-weight: 700;">LUMINIX</span>
        </div>
        <p style="color: var(--muted); font-size: 13px; margin-bottom: 32px;">Real-world RL environment for Accounts Payable automation.</p>
        <div class="pill-row">
            <span class="pill">RL Environment</span> 
            <span class="pill">SOC2 Compliant</span>
            <span class="pill">OCR Pipeline</span>
        </div>
    </div>
    <div class="main">
        <div class="hero">
            <h1>Invoice Compliance Arena</h1>
            <p>High-fidelity AI agent evaluation for complex back-office workflows.</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card"><div class="stat-val">10</div><div class="stat-label">Scenarios</div></div>
            <div class="stat-card"><div class="stat-val">3</div><div class="stat-label">Difficulties</div></div>
            <div class="stat-card"><div class="stat-val">4</div><div class="stat-label">Policy Gates</div></div>
            <div class="stat-card"><div class="stat-val">0.99</div><div class="stat-label">Score Cap</div></div>
        </div>

        <div class="section-title">Core Task Curriculum</div>
        <div class="task-list">
            <div class="task-item">
                <div class="task-name">exact_match_audit</div>
                <div class="task-meta">3 scenarios <span class="tag-easy">EASY</span></div>
            </div>
            <div class="task-item">
                <div class="task-name">fuzzy_reconciliation</div>
                <div class="task-meta">3 scenarios <span class="tag-med">MEDIUM</span></div>
            </div>
            <div class="task-item">
                <div class="task-name">discrepancy_fraud</div>
                <div class="task-meta">4 scenarios <span class="tag-hard">HARD</span></div>
            </div>
        </div>

        <div class="section-title">Global Reward Function</div>
        <div class="reward-box">
            0.6·correct_decision + 0.4·audit_accuracy - 0.3·penalty
        </div>

        <div class="section-title">Sample Audit Log</div>
        <div class="audit-trail">
            <div class="audit-line"><span class="audit-step">STEP 1</span> <span>select_po</span> <span style="color: var(--muted)">po_id=PO-5001</span> <span class="audit-reward">+0.20</span></div>
            <div class="audit-line"><span class="audit-step">CHECK</span> <span>policy_engine</span> <span style="color: var(--muted)">rule=SOC2_CHECK</span> <span style="color: #ef4444">triggered=TRUE</span></div>
            <div class="audit-line"><span class="audit-step">STEP 2</span> <span>final_decision</span> <span style="color: var(--muted)">decision=REJECT</span> <span class="audit-reward">+0.79</span></div>
            <div style="border-top: 1px solid #1e293b; margin-top: 12px; padding-top: 12px; color: var(--accent)">Cumulative Reward: 0.99</div>
        </div>

        <div class="section-title" style="margin-top: 48px;">API Endpoints</div>
        <div class="endpoints-grid">
            <div class="endpoint-card"><span class="ep-verb">POST</span> /reset<p style="color: var(--muted); font-size: 12px; margin: 8px 0 0 0;">Start episode</p></div>
            <div class="endpoint-card"><span class="ep-verb">POST</span> /step<p style="color: var(--muted); font-size: 12px; margin: 8px 0 0 0;">Submit action</p></div>
            <div class="endpoint-card"><span class="ep-verb">GET</span> /tasks<p style="color: var(--muted); font-size: 12px; margin: 8px 0 0 0;">List curriculum</p></div>
        </div>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
@app.get("/web", response_class=HTMLResponse)
async def home(request: Request):
    return HTML_CONTENT

class ResetRequest(BaseModel):
    task_id: str = "easy-exact-match"

@app.post("/reset")
async def reset(req: ResetRequest):
    episode_id = str(uuid.uuid4())
    obs = env.reset(req.task_id)
    return {
        "episode_id": episode_id,
        "task_id": req.task_id,
        "observation": obs,
        "stage": env.state.stage,
        "allowed_action_types": env.get_allowed_action_types()
    }

@app.post("/step")
async def step(episode_id: str, action: dict):
    obs, reward, done, info = env.step(action)
    return {
        "observation": obs, "reward": reward, "done": done, "info": info,
        "stage": env.state.stage, "allowed_action_types": env.get_allowed_action_types()
    }

@app.get("/tasks")
async def tasks():
    from .tasks import _SCENARIOS
    return {"tasks": list(_SCENARIOS.keys())}

@app.get("/health")
async def health():
    return {"status": "healthy"}
