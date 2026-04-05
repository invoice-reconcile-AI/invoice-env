# Invoice Reconciliation AI Agent

> **Meta Hackathon Submission** — OpenEnv AI environment for automated Invoice-to-Payment reconciliation powered by Llama 3.3.

An AI agent receives an **Invoice**, a matching **Purchase Order (PO)**, and a **Goods Received Note (GRN)**, then identifies discrepancies and decides the correct action (`approve`, `flag_discrepancy`, or `reject`).

---

## Team

| Name | Role |
|------|------|
| Mathir | Environment design & server implementation |
| Dharshini | Inference agent & evaluation harness |

---

## Finance-ops Use Case

Accounts-payable teams manually reconcile hundreds of vendor invoices every week. Common problems:

| Problem | Example |
|---------|---------|
| Price mismatch | Vendor charges $1,200/unit; PO says $1,100 |
| Quantity mismatch | Invoice bills for 10 units; only 8 were delivered |
| Vendor name variation | `ACME Supplies Ltd` vs `Acme Supplies Ltd.` |
| Extra charges | `Extended Warranty` on invoice but not in PO |
| Partial delivery | GRN shows fewer items than invoiced |

---

## Benchmark Tasks

| Task ID | Difficulty | Description |
|---------|-----------|-------------|
| `easy-exact-match` | Easy | Perfect PO match; everything matches precisely. |
| `medium-fuzzy-match` | Medium | Small discrepancies (fuzzy vendor name match, small price delta). |
| `hard-discrepancy-detection` | Hard | Vendor mismatch + partial delivery missing items + overcharges. |
| `ambiguous-split-invoice` | Hard | No PO reference; overlapping PO items requiring deduction. |

---

## Scoring (per task, 0.0–1.0)

| Component | Points | Criterion |
|-----------|--------|-----------|
| Correct action type | +0.5 | `approve` / `flag_discrepancy` / `reject` |
| Correct PO linked | +0.2 | `matched_po_id` matches the PO |
| Discrepancy reasoning | +0.3 | Reasoning mentions specific keywords e.g. `price_mismatch`, `extra_charge` |

---

## Agent Strategy

The agent uses **Llama 3.3 70B** via Groq (or Together AI / OpenAI) with a carefully engineered system prompt that:

1. **Teaches the 3-tier decision logic** — approve vs flag vs reject thresholds
2. **Enforces structured JSON output** — `action_type`, `matched_po_id`, `discrepancy_flags[]`, `reasoning`
3. **Maximises all 3 scoring components** — the prompt explicitly lists the rubric (+0.5/+0.2/+0.3) so the model understands what counts
4. **Uses specific discrepancy keywords** — the system prompt lists all valid flag names so the model uses them verbatim in reasoning

---

## Quick Start

### Requirements

- Python 3.10+
- An API key from [Groq](https://console.groq.com), [Together AI](https://api.together.xyz), or [OpenAI](https://platform.openai.com)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set your LLM_API_KEY, LLM_PROVIDER, LLM_MODEL
```

### 3. Start the environment server

```bash
# Option A — plain Python
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

# Option B — Docker
docker build -t invoice-env .
docker run -p 8000:8000 invoice-env
```

### 4. Run the inference agent

```bash
# Run all three tasks
python inference.py

# Run a single task
python inference.py --task easy-exact-match
python inference.py --task medium-fuzzy-match
python inference.py --task hard-discrepancy-detection

# Override provider/model from CLI
python inference.py --provider groq --model llama-3.3-70b-versatile
```

### 5. Run the full evaluator

```bash
python evaluator.py
```

---

## Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ENV_BASE_URL` | No | FastAPI server URL | `http://localhost:8000` |
| `LLM_PROVIDER` | Yes | LLM backend | `groq` / `together` / `openai` |
| `LLM_API_KEY` | Yes | API key for your provider | `gsk_...` |
| `LLM_MODEL` | Yes | Model identifier | `llama-3.3-70b-versatile` |

See `.env.example` for a template.

---

## Project Structure

```
invoice-env/
├── .env.example          # Environment variable template (copy to .env)
├── Dockerfile
├── README.md
├── requirements.txt      # Python dependencies
├── inference.py          # Main inference script (OpenEnv benchmark harness)
├── evaluator.py          # Batch evaluation across all tasks
├── openenv.yaml          # OpenEnv task spec
├── agent/
│   └── agent.py          # Standalone agent (verbose mode, for development)
└── server/
    ├── env.py            # OpenEnv logic: reset(), step(), state(), scoring
    ├── main.py           # FastAPI application
    └── models.py         # Pydantic models (Invoice, PO, GRN, Action, etc.)
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/tasks` | List all available tasks |
| `POST` | `/reset` | Start a new episode `{"task_id": "..."}` |
| `POST` | `/step` | Submit an action and get next observation |
| `GET` | `/state` | Current observation without advancing |

Interactive docs: **http://localhost:8000/docs** (Swagger UI)

---

## Dense Reward Design (Step-wise Grader)

Unlike generic end-of-episode pass/fail systems, this OpenEnv relies on native Reinforcement Learning incremental feedback throughout the pipeline loop:

| Action Trajectory | Incremental Reward |
|---------|--------|
| **Stage 1**: Selecting correct PO | `+0.20` |
| **Stage 2**: Each correct item match | `+0.10` / item |
| **Stage 3**: Valid discrepancy flag | `+0.10` / flag |
| **Stage 3**: Incorrect / Spurious discrepancy | `-0.05` / flag |
| **Stage 4**: Final decision correctness | `+0.30` |
| **Cumulative Assessment** | **Normalized out of 1.0** |

---

## Known Limitations

- The environment has 3 fixed scenarios (easy / medium / hard). A production version would use dynamically generated invoices.
- The agent is single-step (one LLM call per episode). Multi-step reasoning could improve hard task performance.
