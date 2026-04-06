# 🧠 Invoice Reconciliation OpenEnv Environment

> **Meta Hackathon Submission** — A production-grade OpenEnv environment simulating invoice-to-payment reconciliation used in real-world finance systems.

---

## 🚀 OpenEnv Environment Overview

This project implements a **multi-step OpenEnv environment** that models a real-world invoice reconciliation workflow.

Unlike simple classification tasks, this environment requires an AI agent to:

1. Select the correct Purchase Order (PO)
2. Compare invoice line items
3. Detect discrepancies (price, quantity, extra charges)
4. Make a final decision (approve / flag / reject)

This reflects real enterprise decision pipelines used in accounts payable systems.

---

## 👥 Team

| Name       | Role                                                    |
|------------|---------------------------------------------------------|
| Mathir     | Environment design & backend                            |
| Dharshini  |  Inference agent, evaluation, deployment & integration  |
| Harish     | Testing & validation                                    |

---

## 💼 Real-World Problem

Accounts payable teams manually verify invoices against:

* Purchase Orders (PO)
* Goods Received Notes (GRN)

Common issues include:

* Price mismatch
* Quantity mismatch
* Vendor name variations
* Extra charges not in PO
* Partial deliveries

This process is **slow, error-prone, and costly**.

---

## 🏗️ Environment Design

The environment simulates a structured decision pipeline:

### Stages:

* `select_po` → identify correct PO
* `compare_item` → validate line items
* `flag_discrepancy` → detect inconsistencies
* `final_decision` → approve / flag / reject

The environment is **stateful**, evolving after each step.

---

## 📦 Action Space

Agents can take structured actions:

* `select_po`
* `compare_item`
* `flag_discrepancy`
* `final_decision`

All actions are validated using typed models.

---

## 👀 Observation Space

Each step provides:

* Invoice details
* Available Purchase Orders
* GRN (Goods Received Note)
* Previous comparisons
* Detected discrepancies
* Current stage

---

## 🎯 Tasks

| Task ID                    | Difficulty | Description                  |
| -------------------------- | ---------- | ---------------------------- |
| easy-exact-match           | Easy       | Perfect invoice-PO match     |
| medium-fuzzy-match         | Medium     | Minor discrepancies          |
| hard-discrepancy-detection | Hard       | Multiple inconsistencies     |
| ambiguous-split-invoice    | Hard       | Multiple possible PO matches |

---

## 🎯 Reward Function

The environment provides **dense, step-wise rewards**:

* +0.20 → Correct PO selection
* +0.10 → Correct item comparison
* +0.10 → Valid discrepancy flag
* +0.30 → Correct final decision
* −0.60 → Incorrect final decision
* −0.10 → Incorrect PO selection
* −0.05 → Spurious discrepancy flag

Final score is normalized to **[0,1]**.

This enables learning across the entire decision trajectory.

---

## 🤖 Agent Strategy

The agent uses LLM-based reasoning to:

* Match invoice with correct PO
* Compare structured financial data
* Identify discrepancies using defined categories
* Optimize decision based on reward signals

Supports multiple providers:

* Groq
* OpenAI
* Together AI

---

## ⚙️ API Endpoints

| Method | Endpoint  | Description         |
| ------ | --------- | ------------------- |
| `POST` | `/reset`  | Start a new episode |
| `POST` | `/step`   | Take an action      |
| `GET`  | `/state`  | Get current state   |
| `GET`  | `/health` | Health check        |

👉 Swagger UI:
https://dharshinik1-luminix-invoice-env.hf.space/docs

---

## 🐳 Deployment

Deployed using Docker on Hugging Face Spaces.

### Run locally:

```bash
docker build .
docker run -p 8000:8000 <image>
```

---

## 🖥️ Interactive UI

The environment includes a lightweight dashboard to visualize the agent’s decision-making process in real time.

It allows users to:

* Initialize tasks (easy / medium / hard)
* Execute step-by-step actions
* View AI reasoning and validation results
* Observe reward progression and final decision

This transforms the environment from a backend API into an interpretable system for debugging and evaluation.

---

### 🧪 Baseline Inference

To run the baseline agent:

```bash
pip install -r requirements.txt
python inference.py
```

Make sure the environment server is running:

```bash
uvicorn server.main:app --reload
```

Output format:

```
[START]
[STEP]
[STEP]
[END]
```

Complies with OpenEnv evaluation requirements.

---

## 📁 Project Structure

```
invoice-env/
├── Dockerfile
├── README.md
├── requirements.txt
├── inference.py
├── openenv.yaml
└── server/
    ├── main.py
    ├── env.py
    └── models.py
```

---

## 🌍 Real-World Impact

Invoice reconciliation is critical for:

* Preventing financial errors
* Detecting fraud
* Improving operational efficiency
* Automating enterprise workflows

This environment enables training AI agents for **real-world financial decision-making**, not toy problems.

---

## 🏁 Why This Matters

Most RL environments are synthetic or game-based.

This project bridges the gap by:

* Modeling a real enterprise workflow
* Enforcing structured reasoning
* Providing multi-step decision evaluation


---

## 🚀 Conclusion

This environment demonstrates how OpenEnv can be used to simulate **production-grade workflows**, enabling development of intelligent agents for real business applications.

---

## 📌 Notes

* Designed to run under constrained resources (CPU, <20 min runtime)
* Fully compliant with OpenEnv-style interaction patterns
* Supports reproducible evaluation via inference script
