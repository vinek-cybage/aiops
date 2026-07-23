# AIOps Demo

An AI-powered incident management system for a simulated ecommerce platform. A load generator injects realistic faults, fires a webhook with logs and trace context, and an LLM automatically creates incidents with root cause hypotheses, evidence, and team routing.

---

## Architecture

```
load-gen/generate.py
  │  generates logs to stdout
  │  injects faults (ERROR spans)
  └─ POST /api/webhook/grafana
       │  payload: alert + logs + trace
       ▼
aiops  (FastAPI + Claude via Bedrock)
  │  reads context from payload
  │  calls LLM to analyze
  └─ saves incident to PostgreSQL (aiops-db)

telemetry-api  (.NET 8 minimal API)
  │  POST /api/logs | /api/traces | /api/metrics
  └─ writes logs/traces/metrics into the same aiops-db

Containers:
  aiops-db    :5432 — shared Postgres (incidents + teams/users + telemetry)
  aiops-backend :8000 — Python FastAPI backend + web UI
  telemetry-api :5080 — .NET logs/traces/metrics ingestion API

LLM call observability (prompts, completions, latency, tokens) goes to
Langfuse Cloud (https://cloud.langfuse.com) — not a local container.
```

---

## How to Run

### 1. Set up your `.env`
```bash
cp .env.example .env
```
Sign up at [Langfuse Cloud](https://cloud.langfuse.com) (or the US region at `us.cloud.langfuse.com` — update `LANGFUSE_HOST` to match), create a project, and fill in `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` from Settings -> API Keys. The rest have working local defaults. Langfuse tracing is optional — if you leave the keys blank, `agent.py` skips it silently.

### 2. Log in to AWS (Bedrock access, needed by aiops-backend)
```bash
aws sso login --profile AI
```
The container mounts `~/.aws` read-only so it can reuse this cached SSO session — no AWS setup happens inside the container itself. If the token expires, re-run this and restart the `aiops-backend` container:
```bash
podman compose restart aiops-backend
```

### 3. Start all containers
```bash
podman compose up -d --build
```
Run this from the project root — `compose.yaml` and `.env` both live there now, so compose picks up `.env` automatically with no extra flags.

This builds and starts everything: `aiops-db`, `aiops-backend` (Python), and `telemetry-api` (.NET).

- AIOps UI: `http://localhost:8000`
- Telemetry API: `http://localhost:5080/api/health`
- Langfuse (LLM call traces): `https://cloud.langfuse.com` — hosted, not part of this stack

### 3. Run a scenario (second terminal)
```bash
cd load-gen

python demo.py fault "Cascade Failure"       # continuous traffic + fault (Ctrl+C to stop)
python demo.py once  "Payment Gateway Down"  # single shot, exits after one round
python demo.py run   "DB Pool Exhausted"     # fault + waits + prints incident
python demo.py list                          # show all fault names
```

---

## Logs

Every log line follows this format:
```
2026-07-22 11:22:02 INFO     [product-service] GET /api/products/search | query="shoes" | results=39 | latency=102ms | trace_id=4072ff...
```

**Fields:** `timestamp | level | [service] | message | key=value pairs | trace_id=<hex>`

### Normal traffic (INFO only)

Four user journeys run continuously in the background:

| Journey | Services | Sample log |
|---|---|---|
| Browse | product-service | `GET /api/products/search \| query="shoes" \| latency=102ms` |
| Add to cart | product, cart, inventory | `POST /api/cart/add \| user=usr_58684 \| qty=1` |
| Checkout | cart, order, inventory, payment, notification | `charge \| amount=156.94 \| status=approved` |
| Order status | order, notification | `GET /api/orders/ord_166257 \| status=shipped` |

### Fault logs (ERROR / WARN / CRITICAL)

Each fault injects specific log lines alongside normal traffic:

| Fault | Services | Levels | Sample |
|---|---|---|---|
| Payment Gateway Down | payment, order | CRITICAL, ERROR | `Gateway unreachable \| endpoint=stripe.api \| retry=1/3 \| circuit_breaker=OPEN` |
| Auth / JWT Failures | cart | ERROR, WARN, CRITICAL | `JWT validation failed \| reason=token_expired \| ip=10.0.x.x` |
| DB Pool Exhausted | order | WARN, ERROR, CRITICAL | `DB pool exhausted \| max_capacity=50 \| queued=58 \| timeout=30s` |
| Inventory Race Condition | inventory | ERROR, CRITICAL, WARN | `Oversell detected \| product=4821 \| stock=-3` |
| Cascade Failure | payment, order, cart, product | CRITICAL, ERROR, WARN | 4 services each logging their view of the failure |
| High Latency / SLA Breach | product | WARN, ERROR | `p99=4850ms \| SLA_breach=true`, retry storm |
| Memory / OOM Pressure | order | WARN, ERROR, CRITICAL | `Heap climbing \| used=91%` → `OOM imminent` |
| Shipping API Down | notification | ERROR, CRITICAL | `FedEx unreachable \| retry=3/3` |

---

## Traces

Traces are text representations of a span waterfall — each line is one span showing service, operation, error status, and duration.

### Format
```
TRACE <trace_id>:
  [service-name] span-name [ERROR?] duration=Xms | key=value | key=value
```

### Example — Cascade Failure
```
TRACE a3f9c2d1...:
  [payment-service] cascade_root [ERROR] duration=41ms  | error=Cascade failure
  [order-service]   checkout     duration=15ms          | downstream=payment-service
  [cart-service]    get_cart     duration=9ms
  [product-service] browse       duration=7ms           | upstream_errors=cascading
```

### Example — Payment Gateway Down
```
TRACE 7145d9...:
  [payment-service] charge [ERROR] duration=38ms | error=gateway_timeout | payment.amount=245.99
  [order-service]   create_order  duration=12ms  | order.id=ord_882341
```

### Example — Checkout (normal, no fault)
```
TRACE f75869...:
  [cart-service]         get_cart      duration=18ms
  [order-service]        create_order  duration=34ms
  [inventory-service]    reserve_stock duration=28ms
  [payment-service]      charge        duration=180ms | payment.method=paypal | status=approved
  [notification-service] send_email    duration=12ms
```

---

## Span Errors

Span errors are set explicitly on the root span of each fault. They identify where the failure originated.

| Fault | Span name | Error message |
|---|---|---|
| Payment Gateway Down | `charge` | `gateway_timeout` |
| Auth / JWT Failures | `auth_check` | `JWT validation failed` |
| DB Pool Exhausted | `db_query` | `DB pool exhausted` |
| Inventory Race Condition | `reserve_stock` | `Oversell detected` |
| Cascade Failure | `cascade_root` | `Cascade failure` |
| High Latency / SLA Breach | `search` | `p99=Xms SLA breach` |
| Memory / OOM Pressure | `process_orders` | `OOM imminent` |
| Shipping API Down | `send_shipping_update` | `Shipping API unreachable` |

---

## Deterministic vs Non-deterministic

| Part | Behaviour | What varies |
|---|---|---|
| Log structure and field names | Deterministic | — |
| Log values | Non-deterministic | IP address, heap %, p99, retry count, product ID, amounts |
| trace_id | Non-deterministic | Random 128-bit hex each invocation |
| Which fault fires | Deterministic | Set by `--fault` argument |
| Webhook trigger | Deterministic | Always fires on first ERROR span per fault |
| Cooldown | Deterministic | 60s between re-fires for same fault |

---

## When the Webhook Fires

```
Fault injector called
  → log lines printed to stdout
  → _fire_webhook() checks 60s cooldown per (service, alertname)
    → if allowed: background thread POSTs to AIOps
      → AIOps returns 202 immediately
        → background task: reads context, calls LLM, saves incident
```

In **continuous mode** (`python demo.py fault "..."`):
- Fault runs every ~3 seconds (every 6th tick at rate=2)
- Webhook fires once, then suppressed for 60 seconds
- After 60s, fires again if fault is still active — LLM updates existing incident rather than creating a duplicate

---

## Webhook Payload Structure

```json
{
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname":    "Cascade Failure",
      "severity":     "critical",
      "app":          "demo-service",
      "service_name": "payment-service",
      "trace_id":     "a3f9c2d1...",
      "alert_source": "trace"
    },
    "annotations": {
      "summary":     "Cascade Failure on payment-service",
      "description": "payment-service down, cascade spreading to order -> cart -> product"
    },
    "startsAt": "2026-07-22T11:22:02Z"
  }],
  "context": {
    "logs": [
      "2026-07-22 11:22:02 CRITICAL [payment-service] Service down | circuit_breaker=OPEN | trace_id=a3f9c2...",
      "2026-07-22 11:22:02 ERROR    [order-service] payment-service unreachable | retry=3/3 | trace_id=a3f9c2...",
      "2026-07-22 11:22:02 ERROR    [cart-service] order-service timeout | downstream_degraded | trace_id=a3f9c2...",
      "2026-07-22 11:22:02 WARN     [product-service] Elevated error rate | p99=1800ms | trace_id=a3f9c2..."
    ],
    "traces": [
      "TRACE a3f9c2...:",
      "  [payment-service] cascade_root [ERROR] duration=41ms | error=Cascade failure",
      "  [order-service]   checkout     duration=15ms | downstream=payment-service",
      "  [cart-service]    get_cart     duration=9ms",
      "  [product-service] browse       duration=7ms | upstream_errors=cascading"
    ]
  }
}
```

### Fields

| Field | Description |
|---|---|
| `alerts[].labels.alertname` | Human-readable alert name |
| `alerts[].labels.severity` | `critical` or `high` (see below) |
| `alerts[].labels.service_name` | Root service where the fault originated |
| `alerts[].labels.trace_id` | Hex trace ID linking logs to trace spans |
| `alerts[].labels.alert_source` | Always `trace` — triggered by span error |
| `alerts[].annotations.description` | One-line description of what happened |
| `context.logs` | Log lines for this trace, newest fault first |
| `context.traces` | Span waterfall for this trace |

---

## Severity Levels

| Severity | Meaning | Faults |
|---|---|---|
| `critical` | Full outage — service completely down, data integrity broken, or cascade in progress | Payment Gateway Down, Cascade Failure, DB Pool Exhausted |
| `high` | Degraded service — SLA breach, elevated error rate, resource pressure | Auth Failures, High Latency, OOM Pressure, Shipping API Down, Inventory Race |

---

## Incident Structure (AIOps output)

After the LLM processes the webhook, an incident is saved with:

```json
{
  "inc_id": "INC-0001",
  "title": "payment-service Circuit Breaker OPEN Cascade Failure",
  "severity": "critical",
  "services": ["payment-service", "order-service"],
  "team": "payments-platform",
  "hypotheses": [
    { "confidence": 91, "text": "payment-service crashed causing circuit breaker to trip..." },
    { "confidence": 42, "text": "downstream dependency became unavailable..." }
  ],
  "evidence": [
    { "type": "log",     "label": "payment-service CRITICAL", "text": "Service down | circuit_breaker=OPEN..." },
    { "type": "trace",   "label": "cascade_root span",        "text": "[payment-service] cascade_root [ERROR] duration=41ms" },
    { "type": "pattern", "label": "Cascade detection",        "text": "order-service errors are 1:1 with payment-service failures by trace_id" }
  ],
  "ai_summary": "payment-service entered a full outage at 11:22:02Z...",
  "timeline": [
    { "time": "11:22:38", "event": "Logs analyzed by AI agent" },
    { "time": "11:22:38", "event": "Root cause hypotheses generated" },
    { "time": "11:22:38", "event": "Routed to payments-platform" }
  ]
}
```

---

## Project Structure

```
Hackathon/
├── compose.yaml          — aiops-db, aiops-backend, telemetry-api
├── .env                  — AWS/Bedrock + Langfuse Cloud keys, shared by all services (never commit)
├── .env.example
├── .gitignore            — single project-wide gitignore
├── .dockerignore         — single project-wide dockerignore (both Dockerfiles build from repo root)
│
├── load-gen/
│   ├── generate.py       — load generator + fault injectors + webhook firing
│   ├── demo.py           — CLI: normal / fault / once / run / list
│   ├── requirements.txt  — only: requests
│   └── .venv/            — Python venv (used only if running load-gen locally)
│
├── telemetry-api/         — .NET 8 minimal API (logs/traces/metrics → aiops-db)
│   ├── Program.cs
│   ├── telemetry-api.csproj
│   └── Dockerfile         — build context is the project root
│
├── web/                   — served by aiops-backend at "/" (FRONTEND_DIR)
│   ├── index.html
│   ├── app.js
│   └── style.css
│
└── aiops/
    ├── main.py           — FastAPI, webhook handler, Loki/Tempo fetch (live mode)
    ├── agent.py          — LLM prompt + Bedrock call
    ├── incidents.py      — PostgreSQL incident CRUD
    ├── database.py       — DB init + schema
    ├── teams.py          — Team + user management
    ├── requirements.txt
    ├── start.sh          — run locally (outside Docker) with AWS_PROFILE=AI
    └── Dockerfile         — build context is the project root, so it can also COPY web/
```

---

## Ports

| Service | URL | Purpose |
|---|---|---|
| AIOps UI | `http://localhost:8000` | Incident dashboard |
| Telemetry API | `http://localhost:5080` | .NET logs/traces/metrics ingestion |
| aiops-db (Postgres) | `localhost:5432` | Shared DB — incidents, teams/users, telemetry |
| Langfuse | `https://cloud.langfuse.com` | LLM call traces (hosted, not part of this stack) |
