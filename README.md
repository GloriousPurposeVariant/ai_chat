# Reelo AI Chat

> AI-powered B2B chat service for GW Products. Routes natural-language questions about sales, compliance, stock, and vendor onboarding to the right tools, then uses Gemini 2.5 Flash to explain the results in plain English.

---

## Prerequisites

- Python 3.12+ (or Docker)
- A **Gemini API key** — [get one free at Google AI Studio](https://aistudio.google.com/)

---

## Quick Start (one command)

### 🐳 With Docker (recommended)

```bash
# 1. Add your key
echo "GEMINI_API_KEY=your_key_here" > .env

# 2. Build & run
docker compose up --build
```

Server is live at **http://localhost:8000**

---

### 🐍 Without Docker (local Python)

```bash
# 1. Create & activate virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Add your key
cp .env.example .env
# Open .env and set: GEMINI_API_KEY=your_key_here

# 4. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Server is live at **http://localhost:8000**

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ Yes | Google Gemini API key |

Copy `.env.example` to `.env` and fill in the value.

---

## Running the Test Queries

Make sure the server is running first (port 8000), then in a **separate terminal**:

### Full integration test (5 queries + basket check)

```bash
# Activate your venv if running locally
source .venv/bin/activate

python tests/test_queries.py
```

This runs 6 chained scenarios end-to-end:
1. **Sales** — Hot picks for CA under $5,000
2. **Compliance** — Why is SKU-1002 blocked in MA? (with alternatives)
3. **Ops** — Stock check for SKU-1003 across warehouses
4. **Vendor onboarding** — Missing Net Wt + no lab report
5. **Memory follow-up** — "Add 2 of the first one to the basket"
6. **Basket view** — Final basket state via `GET /basket/{session_id}`

### Smoke test (single request)

```bash
python tests/test.py
```

Sends one sales query and prints the raw JSON response.

### With Docker (tests against running container)

```bash
# In one terminal — start the service
docker compose up

# In another terminal — run tests
docker exec ai_chat_app python tests/test_queries.py
# or run from your local machine if Python is available:
python tests/test_queries.py
```

### Using curl

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hot picks under $500 in CA","user_type":"portal_customer"}' | python -m json.tool
```

### Interactive API docs

Visit **http://localhost:8000/docs** — FastAPI's built-in Swagger UI lets you try all endpoints.

---

## Architecture Overview

```
POST /chat
    │
    ├─ validate_user_type()          permissions.py   Unknown types → portal_customer (safe default)
    ├─ get_or_create_session()       state.py         Restore last_state, budget, product_ids, basket
    │
    ├─ is_basket_followup()?         router.py        "add 2 of the first one" → short-circuit, no LLM
    │
    ├─ classify_intent()             router.py        Keyword trie first → LLM fallback (Gemini)
    ├─ extract_state/budget/ids()    router.py        Regex entity extraction
    │
    ├─ check_permission()            permissions.py   RBAC allowlist — 403 if tool not permitted
    │
    ├─ chain_sales()                 chains.py        hot_picks → compliance_filter → LLM
    ├─ chain_compliance()            chains.py        compliance_filter → (alternatives) → LLM
    ├─ chain_vendor()                chains.py        vendor_validate → LLM
    ├─ chain_ops()                   chains.py        stock_by_warehouse → LLM
    └─ chain_kb()                    chains.py        kb_search → LLM
         │
         ├─ update_session()         state.py         Persist turn context
         └─ log_request()            observability.py Emit structured JSON log line
```

### Where things live

| Concern | File | Key symbols |
|---|---|---|
| **Routing / intent** | `app/router.py` | `classify_intent()`, `INTENT_KEYWORDS`, `_llm_classify_intent()` |
| **Tools** | `app/tools.py` | `hot_picks`, `compliance_filter`, `stock_by_warehouse`, `vendor_validate`, `kb_search` |
| **Chains** | `app/chains.py` | `chain_sales`, `chain_compliance`, `chain_vendor`, `chain_ops`, `chain_kb` |
| **Session state** | `app/state.py` | `SESSIONS` dict, `get_or_create_session()`, `update_session()`, `add_to_basket()` |
| **Permissions / RBAC** | `app/permissions.py` | `TOOL_ALLOWLIST`, `check_permission()`, `redact_pii()` |
| **Observability** | `app/observability.py` | `log_request()`, `make_tool_record()`, `estimate_tokens()` |
| **LLM** | `app/llm.py` | `get_llm()` → Gemini 2.5 Flash, `format_response()` |
| **Entrypoint** | `main.py` | FastAPI app, `/chat`, `/basket/{session_id}` |
| **Seed data** | `data/seed_data.json` | Products, inventory, vendors, KB docs |

### RBAC at a glance

| Tool | `portal_customer` | `portal_vendor` | `internal_sales` |
|---|:---:|:---:|:---:|
| hot_picks | ✅ | ❌ | ✅ |
| compliance_filter | ✅ | ❌ | ✅ |
| kb_search | ✅ | ✅ | ✅ |
| vendor_validate | ❌ | ✅ | ✅ |
| stock_by_warehouse | ❌ | ❌ | ✅ |

### Observability log format

Every request emits a single-line JSON to stdout:

```json
{
  "request_id": "uuid",
  "session_id": "uuid",
  "timestamp": "2026-04-18T10:00:00Z",
  "user_type": "internal_sales",
  "intent": "SALES_RECO",
  "tools_called": ["hot_picks", "compliance_filter"],
  "tool_details": [
    {"tool": "hot_picks", "args": {"state": "CA", "budget": 5000}, "latency_ms": 3, "result_size": 5},
    {"tool": "compliance_filter", "args": {"state": "CA", "product_ids": [...]}, "latency_ms": 1, "result_size": 5}
  ],
  "total_latency_ms": 812,
  "prompt_tokens_estimate": 340
}
```

Grep for `[OBSERVABILITY]` in logs to extract these lines.

---

## API Reference

### `POST /chat`

| Field | Type | Default | Description |
|---|---|---|---|
| `message` | string | required | Natural language user query |
| `session_id` | string | auto-generated | Pass back to continue a conversation |
| `user_type` | string | `portal_customer` | `portal_customer` · `portal_vendor` · `internal_sales` |
| `vendor_attributes` | object | null | Structured product data for vendor onboarding |

**Response:** `session_id`, `intent`, `response`, `tools_called`, `latency_ms`, `prompt_tokens_est`

### `GET /basket/{session_id}`

Returns enriched basket with SKU, name, unit price, and line totals.

### `GET /`

Health check.

---

## Project Structure

```
ai_chat/
├── main.py                 # FastAPI app — entrypoint & orchestration
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── app/
│   ├── router.py           # Intent classification + entity extraction
│   ├── chains.py           # 5 LLM chains (one per intent)
│   ├── tools.py            # 5 deterministic tool functions
│   ├── state.py            # In-memory session store
│   ├── permissions.py      # RBAC allowlists + PII redaction
│   ├── observability.py    # Structured logging
│   └── llm.py              # Gemini 2.5 Flash wrapper
├── data/
│   └── seed_data.json      # Products, inventory, KB docs
└── tests/
    ├── test.py             # Single smoke-test request
    └── test_queries.py     # Full 5-query integration suite
```

---

## Notes

- **Session state is in-memory.** It resets when the server restarts. For production, replace `SESSIONS` in `state.py` with Redis or a database.
- **No external database.** All product, inventory, and KB data is loaded from `data/seed_data.json` at startup.
- **PII is redacted** before any data reaches the LLM — see `redact_pii()` in `permissions.py`.