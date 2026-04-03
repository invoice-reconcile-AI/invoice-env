# invoice-env

OpenEnv AI environment for automated **Invoice-to-Payment reconciliation**.  
An AI agent receives an Invoice, a matching Purchase Order (PO), and a Goods
Received Note (GRN), then must identify discrepancies and decide the correct
action (approve, reject, flag, etc.).

---

## Finance-ops use case

Accounts-payable teams manually reconcile hundreds of vendor invoices every
week against approved POs and warehouse receipts.  Common problems include:

| Problem | Example |
|---------|---------|
| Price mismatch | Vendor charges $1,200/unit; PO says $1,100 |
| Quantity mismatch | Invoice bills for 10 units; only 8 were delivered |
| Vendor name variation | "ACME Supplies Ltd" vs "Acme Supplies Ltd." |
| Extra charges | "Extended Warranty" appears on invoice but not in PO |
| Partial delivery | GRN shows fewer items than invoiced |

This environment trains AI agents to automate that reconciliation work with
three difficulty tiers that mirror real-world complexity.

---

## Tasks

| Task ID | Difficulty | Description |
|---------|-----------|-------------|
| `easy-exact-match` | Easy | Invoice amounts and line items exactly match the PO. Correct action: **APPROVE**. |
| `medium-fuzzy-match` | Medium | Minor vendor-name capitalisation difference + one unit-price overcharge. Correct action: **FLAG_DISCREPANCY**. |
| `hard-discrepancy-detection` | Hard | Multiple discrepancies: price overcharge, partial delivery, extra line item. Correct action: **REJECT**. |

---

## API

The environment exposes a standard OpenEnv HTTP API:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/tasks` | List all available tasks |
| `POST` | `/reset` | Start a new episode (`{"task_id": "..."}`) |
| `POST` | `/step` | Submit an action and receive the next observation |
| `GET` | `/state` | Return current observation without advancing the episode |

Full interactive docs are available at **http://localhost:8000/docs** (Swagger UI)
and **http://localhost:8000/redoc** (ReDoc) once the server is running.

---

## Running locally

### With Docker (recommended)

```bash
docker build -t invoice-env .
docker run -p 8000:8000 invoice-env
```

### Without Docker

```bash
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8000
```

---

## Quick-start example

```bash
# 1. Start a new episode (easy task)
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "easy-exact-match"}' | python3 -m json.tool

# 2. Submit an APPROVE action
curl -s -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{"action_type": "approve", "discrepancy_flags": [], "reasoning": "All amounts match."}' \
  | python3 -m json.tool

# 3. Try the hard task
curl -s -X POST http://localhost:8000/reset \
  -H "Content-Type: application/json" \
  -d '{"task_id": "hard-discrepancy-detection"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/step \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "reject",
    "discrepancy_flags": ["price_mismatch", "quantity_mismatch", "extra_charge"],
    "reasoning": "Price overcharge on laptops, partial delivery on mice, extra warranty charge."
  }' | python3 -m json.tool
```

---

## Project structure

```
invoice-env/
├── Dockerfile
├── README.md
├── openenv.yaml          # Task definitions and environment spec
├── requirements.txt
└── server/
    ├── __init__.py
    ├── env.py            # OpenEnv logic: reset(), step(), state()
    ├── main.py           # FastAPI application
    └── models.py         # Pydantic models
```

---

## Reward scheme

| Outcome | Reward |
|---------|--------|
| Correct action type **and** all discrepancies flagged | `+1.0` |
| Correct action type but incomplete discrepancy flags | `+0.5` |
| Wrong action type | `-1.0` |

