# AIOps Demo

An AI-powered incident management system for a simulated ecommerce platform. The orders service generates structured logs and metrics; an AI worker clusters errors, embeds them via AWS Bedrock, and deduplicates them into incidents viewable on a live dashboard.

---

## Architecture

```
aiops-services  (FastAPI — simulates orders + payments, injects faults)
  │  writes structured logs + metrics rows
  ▼
aiops-db  (PostgreSQL — logs, metrics, incidents, traces, teams, users)
  │
  ├─▶ log-viewer worker  (Drain3 clustering → Bedrock embeddings → incident dedup)
  │       │  writes incidents to Postgres + Neo4j
  │       ▼
  │   aiops-neo4j  (graph of Service / Incident / ErrorPattern nodes + RELATED_TO edges)
  │
  └─▶ log-viewer API  (FastAPI — read-only REST API over incidents + graph)
          │  serves React SPA at /
          ▼
      log-viewer UI  (React + Vite — Dashboard, Incidents table, Graph view)
```

The `log-viewer` container runs **all three** (worker + API + UI) as a single combined service.

---

## Services & Ports

| Service | Host Port | Purpose |
|---|---|---|
| `aiops-db` | `3111` | Shared PostgreSQL |
| `aiops-neo4j` (HTTP) | `3112` | Neo4j browser UI |
| `aiops-neo4j` (Bolt) | `3113` | Bolt driver |
| `aiops-services` | `3114` | Orders + Payments API |
| `log-viewer` | `3115` | Worker + REST API (`/api/*`) + React UI (`/`) |

---

## How to Run

### 1. Copy and configure `.env`
```bash
cp .env.example .env
```
Fill in your AWS credentials for Bedrock access (used by the log-viewer worker for embeddings):
```
AWS_BEARER_TOKEN_BEDROCK=...
```

### 2. Log in to AWS (Bedrock)
```bash
aws sso login --profile AI
```
The container mounts `~/.aws` (read-write — boto3 needs to write refreshed SSO tokens back to `~/.aws/sso/cache/`) to reuse the cached SSO session. If the token expires, re-run this and restart:
```bash
docker compose restart log-viewer
```

### 3. Start all containers
```bash
docker compose up -d --build
```

- **Log Viewer UI**: `http://localhost:3115`
- **API docs (Swagger)**: `http://localhost:3115/docs`
- **Neo4j browser**: `http://localhost:3112`
- **Orders service**: `http://localhost:3114`

Log in with the access code `aiops2026` (cosmetic client-side gate only — not real authentication).

---

## Log Viewer API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/incidents` | List incidents (filter: `?service=X&status=Y`) |
| GET | `/api/incidents/{id}` | Get a single incident |
| GET | `/api/metrics` | Dashboard counts + per-service breakdown |
| GET | `/api/graph` | Neo4j incident relationship graph |

Interactive docs at `http://localhost:3115/docs`.

---

## Orders Service — Fault Injection

Toggle faults via the admin endpoints on `http://localhost:3114`:

| Endpoint | Description |
|---|---|
| `POST /admin/deploy` | Simulate a bad deployment (500s on `GET /orders/{id}`) |
| `POST /admin/rollback` | Roll back the bad deployment |
| `POST /admin/memory-leak/on` | Simulate a memory leak |
| `POST /admin/database-connection-leak/on` | Simulate DB connection leak (pool exhaustion → 500s) |
| `POST /admin/payment-provider/stripe` | Simulate payment provider failures (Stripe) |
| `POST /admin/payment-provider/paypal` | Restore the healthy payment provider (Paypal) |
| `POST /admin/cpu-throttle/on` | Simulate CPU throttling |
| `POST /admin/concurrency-limit/on` | Simulate a concurrency limit (429s) |
| `POST /admin/scale-out` | Disable CPU throttle + concurrency limit |
| `POST /admin/restart-pod` | Clear leaked memory + DB connections |

Only 3 faults reach the log-viewer worker as `ERROR`-level logs (the only level it clusters into incidents): `deploy` (bad pricing calc on `GET /orders/{id}`), `database-connection-leak/on` (pool exhaustion on `GET /orders/{id}`), and `payment-provider/stripe`, which also surfaces as two distinct incidents on the orders side — `POST /orders/{id}/checkout` logs its own `ERROR` when the payment call it makes fails, with a different message depending on whether Stripe returned a gateway error (503) or was unreachable (502). Memory leak, CPU throttle, and concurrency limit only log at `WARN`/`INFO` and won't produce incidents.

---

## Project Structure

```
aiops/
├── Dockerfile              — multi-stage: Node builds React, Python runs worker + API
├── compose.yaml            — all services: aiops-db, aiops-neo4j, aiops-services, log-viewer
├── .env                    — secrets and port overrides (never commit)
├── .env.example
│
├── db/
│   └── init/01_init.sql    — PostgreSQL schema (logs, metrics, incidents, traces, teams, users)
│
├── services/
│   └── python-services/    — orders + payments FastAPI service
│
├── log-viewer/
│   ├── service.py          — polling worker: Drain3 → Bedrock → FAISS → Postgres + Neo4j
│   ├── entrypoint.sh       — starts worker + uvicorn in same container
│   ├── embeddings.py       — AWS Bedrock Titan embedding calls
│   ├── neo4j_store.py      — Neo4j upsert helpers
│   ├── postgres_store.py   — Postgres incident CRUD
│   ├── pull_logs.py        — polls the logs table
│   ├── vector_store.py     — FAISS in-memory incident index
│   └── requirements.txt    — psycopg2, drain3, boto3, faiss-cpu, numpy, neo4j
│
└── log-viewer-ui/
    ├── api/
    │   ├── main.py         — FastAPI: /api/* endpoints + serves React static files
    │   ├── db.py           — Postgres queries
    │   ├── graph.py        — Neo4j queries
    │   └── requirements.txt — fastapi, uvicorn, psycopg2, neo4j
    └── web/                — React + TypeScript + Vite + MUI
        ├── src/
        │   ├── auth/       — AuthProvider (cosmetic sessionStorage login gate)
        │   ├── routes/
        │   │   ├── guards/RequireAuth.tsx — redirects to /login if not authed
        │   │   ├── router.tsx  — routes: /login, /, /incidents, /graph
        │   │   └── AppLayout.tsx — nav (icons, logout) + theme toggle
        │   ├── pages/
        │   │   ├── auth/LoginPage.tsx
        │   │   ├── dashboard/ — stat tiles, StatusDonutChart, service bar chart
        │   │   ├── incidents/
        │   │   └── graph/
        │   ├── components/  — StatTile, ServiceBarChart, StatusDonutChart, ...
        │   └── theme/theme.ts — orange & black brand palette
        └── package.json
```

---

## How Incident Detection Works

1. **Poll** — worker fetches new `ERROR` log rows from Postgres every 5s
2. **Cluster** — Drain3 extracts a structural template from the log message
3. **Embed** — AWS Bedrock Titan generates a 1024-dim vector for the template
4. **Match** — FAISS cosine similarity search (threshold 0.45) against known incidents for the same service
5. **Deduplicate** — match found → bump `occurrences`; no match → new `INC-XXXX` row
6. **Graph** — Neo4j nodes updated; new incidents get at most one `RELATED_TO` edge to the strongest cross-service match
