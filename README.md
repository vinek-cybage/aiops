# AIOps Demo

An AI-powered incident management system for a simulated ecommerce platform. The orders service generates structured logs and metrics; an AI worker clusters errors, embeds them via AWS Bedrock, and deduplicates them into incidents viewable on a live dashboard.

---

## Architecture

```
orders-service  (FastAPI — simulates orders + payments, injects faults)
  │  writes structured logs + metrics rows
  ▼
aiops-db  (PostgreSQL — logs, metrics, incidents, traces, teams, users)
  │
  ├─▶ log-viewer worker  (Drain3 clustering → Bedrock embeddings → incident dedup)
  │       │  writes incidents to Postgres + Neo4j
  │       ▼
  │   neo4j  (graph of Service / Incident / ErrorPattern nodes + RELATED_TO edges)
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
| `neo4j` (HTTP) | `3118` | Neo4j browser UI |
| `neo4j` (Bolt) | `3119` | Bolt driver |
| `orders-service` | `3114` | Orders + Payments API |
| `log-viewer` | `3120` | Worker + REST API (`/api/*`) + React UI (`/`) |

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
The container mounts `~/.aws` read-only to reuse the cached SSO session. If the token expires, re-run this and restart:
```bash
podman compose restart log-viewer
```

### 3. Start all containers
```bash
podman compose up -d --build
```

- **Log Viewer UI**: `http://localhost:3120`
- **API docs (Swagger)**: `http://localhost:3120/docs`
- **Neo4j browser**: `http://localhost:3118`
- **Orders service**: `http://localhost:3114`

---

## Log Viewer API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/incidents` | List incidents (filter: `?service=X&status=Y`) |
| GET | `/api/incidents/{id}` | Get a single incident |
| GET | `/api/metrics` | Dashboard counts + per-service breakdown |
| GET | `/api/graph` | Neo4j incident relationship graph |

Interactive docs at `http://localhost:3120/docs`.

---

## Orders Service — Fault Injection

Toggle faults via the admin endpoints on `http://localhost:3114`:

| Endpoint | Description |
|---|---|
| `POST /admin/fault/bad-deploy` | Simulate a bad deployment |
| `POST /admin/fault/memory-leak` | Simulate a memory leak |
| `POST /admin/fault/db-leak` | Simulate DB connection leak |
| `POST /admin/fault/bad-payment` | Simulate payment provider failures |
| `POST /admin/fault/cpu-throttle` | Simulate CPU throttling |
| `POST /admin/reset` | Reset all faults |

---

## Project Structure

```
aiops/
├── Dockerfile              — multi-stage: Node builds React, Python runs worker + API
├── compose.yaml            — all services: aiops-db, neo4j, orders-service, log-viewer
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
        │   ├── pages/      — Dashboard, Incidents, Graph
        │   └── components/
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
