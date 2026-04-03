---
title: Invoice Reconciliation Environment
emoji: 🧾
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
base_path: /web
tags:
  - openenv
  - finance
---

# Invoice Reconciliation OpenEnv Environment

Enterprise-style OpenEnv environment for Invoice-to-Payment reconciliation.

An agent receives a noisy invoice text, a shortlist of candidate purchase orders,
and goods-received logs. The agent must output one strict JSON action schema:

```json
{ "po_id": "PO-1234", "decision": "pay|hold|flag", "note": "reason" }
```

This repository is structured to pass OpenEnv tooling (`openenv validate`) and to
match the Round 1 evaluation constraints.

## Environment Design

- Domain: Accounts payable reconciliation (real finance ops workflow)
- API: OpenEnv standard `reset()`, `step(action)`, `state()`
- Typed models: Pydantic action/observation/state (+ reward component model)
- Tasks: 3 deterministic tiers (`easy`, `medium`, `hard`)
- Reward shaping: partial progress over 2-step trajectories

## Action Space

The environment accepts one typed action model:

- `po_id: str` — selected purchase order identifier
- `decision: enum(pay|hold|flag)` — approval decision
- `note: str` — short rationale for the decision

## Observation Space

Each `reset()` and `step()` returns a typed observation containing:

- `task_id: str`
- `difficulty: easy|medium|hard`
- `stage: po_selection|final_decision|completed`
- `invoice_text: str`
- `candidate_pos: List[PurchaseOrderCandidate]`
- `grn_log: List[GRNEntry]`
- `allowed_decisions: List[str]`
- `hints: List[str]`
- `accumulated_score: float` in `[0.0, 1.0]`
- `reward: float`, `done: bool`, plus metadata with `final_score`

## State Space

`state()` returns episode state with:

- `episode_id: str`
- `step_count: int`
- `task_id: str`
- `difficulty: str`
- `stage: str`
- `max_steps: int`
- `final_score: float` in `[0.0, 1.0]`
- `po_id_selected: Optional[str]`
- `decision_submitted: Optional[str]`

## Task Set

1. `easy-exact-match`
2. `medium-fuzzy-tolerance`
3. `hard-discrepancy-detection`

## Reward Function (Deterministic)

Final score is clamped to `[0.0, 1.0]` and built from weighted components:

- `+0.3` correct `po_id` linkage
- `+0.4` correct decision (`pay|hold|flag`)
- `+0.3` note quality (keyword coverage)
- `-0.1` penalty for invalid/non-existent `po_id`

Episodes run for up to 2 steps:

1. PO selection step (partial signal)
2. Final decision step (decision + note grading)

## Project Structure

```text
invoice-env/
  __init__.py
  client.py
  models.py
  inference.py
  openenv.yaml
  pyproject.toml
  uv.lock
  Dockerfile
  requirements.txt
  README.md
  outputs/
  scripts/
    smoke_test.py
  server/
    __init__.py
    app.py
    env.py
    environment.py
    main.py
    models.py
```

## Required Environment Variables for Inference

- `API_BASE_URL` (default: `https://router.huggingface.co/v1`)
- `MODEL_NAME` (default: `Qwen/Qwen2.5-72B-Instruct`)
- `HF_TOKEN` (required)

Optional:

- `ENV_BASE_URL` (default: `http://localhost:8000`)
- `LOCAL_IMAGE_NAME` (if set, inference spins env from Docker image)

## Run Locally

### 1) Install

```bash
pip install -r requirements.txt
```

### 2) Start Server

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
```

### 3) Smoke Test

```bash
python scripts/smoke_test.py
```

### 4) Baseline Inference

```bash
export HF_TOKEN=your_token
python inference.py
```

## Docker

```bash
docker build -t invoice-reconciliation-env:latest .
docker run --rm -p 8000:8000 invoice-reconciliation-env:latest
```

## Validation

```bash
openenv validate
python scripts/smoke_test.py
bash scripts/validate-submission.sh
```

Note: `openenv validate --url ...` is available in newer OpenEnv CLIs. The bundled
`scripts/validate-submission.sh` auto-detects CLI capability and falls back to
direct endpoint contract checks when needed.

## Live Deployment

Canonical live Space URL:

- `https://mathir14-invoice-reconciliation-env-v2.hf.space`

Quick sanity check:

```bash
openenv validate --url https://mathir14-invoice-reconciliation-env-v2.hf.space
```

## Baseline Scores

Baseline run (model: `Qwen/Qwen2.5-72B-Instruct`, endpoint: HF router, temperature `0.0`):

- `easy-exact-match`: rewards `0.30,0.70` -> final score `1.00`
- `medium-fuzzy-tolerance`: rewards `0.30,0.70` -> final score `1.00`
- `hard-discrepancy-detection`: rewards `0.30,0.55` -> final score `0.85`

Mean final score across tasks: `0.95`

Raw structured logs are captured in [outputs/baseline.log](outputs/baseline.log).

## Pre-Submission Check

Run the bundled validator before submission:

```bash
bash scripts/validate-submission.sh
```

Optional (also validate your deployed Space URL):

```bash
bash scripts/validate-submission.sh https://mathir14-invoice-reconciliation-env-v2.hf.space
```

## Notes

- The baseline `inference.py` prints only `[START]`, `[STEP]`, and `[END]` lines
  for evaluator compatibility.
- All task generation and grading logic is deterministic.
