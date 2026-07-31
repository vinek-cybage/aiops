# AIOps — Complete System Flow

Reconstructed from the current code (`aiops/`, `orchestrator/`, `telemetry-api/`, `load-gen/`, `web/`),
using `docs/image.png` as the target-state reference. Solid arrows = implemented and wired up today.
Dashed arrows = designed in `image.png` but not yet built.

```mermaid
flowchart TB

    LOADGEN["load-gen/generate.py + demo.py\nsimulated e-commerce traffic\n+ fault injection (8 fault types)"]

    subgraph INGEST["Ingestion"]
        TELAPI[".NET 8 telemetry-api\nPOST /api/logs · /api/traces · /api/metrics"]
    end

    DB[("aiops-db (Postgres)\ntables: logs, traces, metrics, cases, alerts, incidents, teams, users")]

    LOADGEN -->|"stdout logs/traces, fires every ~3s"| TELAPI
    TELAPI -->|"INSERT"| DB

    LOADGEN ==>|"POST /api/webhook/grafana\n(alert + inline logs/traces,\n60s cooldown per service+alert)"| WEBHOOK

    subgraph LEGACY["Path A — Webhook pipeline (aiops-api) — LIVE, wired in compose.yaml"]
        WEBHOOK["FastAPI aiops-api\n/api/webhook/grafana → 202 + background task"]
        FETCH["Gather context:\ninline payload  OR  Loki/Tempo (live mode)  OR  DB (logs/metrics/open cases)"]
        ANALYZE["agent.analyze() — Claude via Bedrock\none shot: parse + hypotheses + evidence\n+ duplicate/cascade decision"]
        SAVEINC["incidents.save_incident()\nnew / updated(duplicate) / cascade"]
        WEBHOOK --> FETCH --> ANALYZE --> SAVEINC
        SAVEINC -->|"INSERT/UPDATE"| DB
    end

    subgraph ORCH["Path B — Orchestrator pipeline — standalone module, NOT in compose.yaml yet"]
        direction TB
        subgraph STAGE1["Stage 1 — poller.py (every POLL_INTERVAL_SECONDS=10s)"]
            DETECT["detectors.py\nerror_rate / p99_latency / connections thresholds\n+ RSS memory trend slope"]
            GROUP["grouping.py\ntime-window sweep per service\n(±GROUPING_WINDOW_SECONDS, default 10s)"]
            SIG["build_signature_text()\ndeterministic text: service+metrics+events+severity"]
            EMBED["embeddings.py\nTitan embed via Bedrock"]
            FAISSIDX[("faiss_index.py\nIndexIDMap(IndexFlatIP)\ncases.id == vector id")]
            DECIDE{"dedup.py\ncosine sim ≥ SIMILARITY_THRESHOLD (0.86)\nvs recent OPEN/INVESTIGATING cases\nof same service?"}
            NEWCASE["insert_case()\nstatus=OPEN, occurrence_count=1"]
            DUPCASE["update_case_on_duplicate()\noccurrence_count += 1"]

            DETECT --> GROUP --> SIG --> EMBED --> DECIDE
            EMBED -.-> FAISSIDX
            DECIDE -->|"no match"| NEWCASE
            DECIDE -->|"match"| DUPCASE
            NEWCASE -->|"index.add + save"| FAISSIDX
        end

        subgraph STAGE2["Stage 2 — summarizer_poller.py (every SUMMARIZER_POLL_INTERVAL_SECONDS=10s)"]
            FETCHCASE["fetch_unsummarized_cases()\nWHERE summarized_at IS NULL"]
            LLMSUM["llm.summarize_case() — Claude via Bedrock\ntitle · ranked hypotheses+confidence · evidence · ai_summary"]
            SAVESUM["save_case_summary()"]
            FETCHCASE --> LLMSUM --> SAVESUM
        end

        DB -->|"new metrics + logs\nsince checkpoint.json"| DETECT
        NEWCASE -->|"INSERT case + alerts"| DB
        DUPCASE -->|"UPDATE case"| DB
        DB -->|"unsummarized cases + their alerts/logs"| FETCHCASE
        SAVESUM -->|"UPDATE case\n(title/hypotheses/evidence/ai_summary)"| DB
    end

    subgraph WEBAPP["Web UI (React SPA, served by aiops-api at '/')"]
        DASH["Dashboard — open/resolved/recurring counts"]
        LIST["Incidents list — filter by status/severity/app/service"]
        DETAIL["Incident detail — hypotheses, evidence, timeline"]
        RESOLVEBTN["'Mark Resolved' button"]
        TEAMS["Teams/Users admin"]
        DETAIL --> RESOLVEBTN
    end

    DB -->|"GET /api/incidents*"| DASH
    DB --> LIST --> DETAIL

    %% ---- Planned, not implemented (from image.png) ----
    subgraph FUTURE["Planned / Stage 3 — NOT implemented in code today"]
        direction TB
        SIMSEARCH["Similarity search:\nLLM case summary  ⟷  library of Action descriptions"]
        ACTIONITEM["Actionable item, e.g.:\n{action: 'Rollback',\n description: 'Bad deployment',\n precondition: '...'}\n1. version rollback vN → vN-1\n2. Raise PR\n3. Config change"]
        POSSOLBTN["'Possible Solutions' button in UI"]

        SIMSEARCH --> ACTIONITEM --> POSSOLBTN
    end

    LLMSUM -.->|"case summary text"| SIMSEARCH
    POSSOLBTN -.-> WEBAPP
    ACTIONITEM -.->|"remediation applied → new signal"| DETECT

    classDef planned stroke-dasharray: 5 5,fill:#f5f5f5,color:#666;
    class SIMSEARCH,ACTIONITEM,POSSOLBTN planned;
```

## Key takeaways

- **Two independent incident pipelines write to the same DB today**: the webhook-driven `aiops-api` path (Path A, single-shot LLM call, live in `compose.yaml`) and the poll-based `orchestrator` path (Path B, split into Stage 1 detect/group/dedup and Stage 2 LLM summarize, **not yet added to `compose.yaml`** — it has its own `Dockerfile` but no service entry). They don't share a table: Path A writes `incidents`, Path B writes `cases`/`alerts`.
- **Path B is the one that matches `image.png`'s left/middle boxes** almost exactly: "Poll Alerts (Grouping) CASES, Time Sensitive (±10s)" = `grouping.py`; "LLM Summarization hypothesis / Title / Supporting Evidence" = `summarizer_poller.py` + `llm.py`.
- **The right-hand half of `image.png`** — similarity search between the LLM summary and a library of remediation actions, the actionable-items block (rollback/PR/config), and the "Possible Solutions" UI button — has no corresponding code anywhere in `aiops/`, `orchestrator/`, or `web/`. It's marked as *planned* (dashed) in the diagram above.
- FAISS dedup uses `cases.id` directly as the vector ID (`IndexIDMap`), with Postgres as source of truth and the index file (`orchestrator/data/cases.faiss`) as a rebuildable cache (`CaseIndex.rebuild_from_db`).
- Both LLM call sites (`aiops/agent.py` and `orchestrator/llm.py`) use Claude on Bedrock and share the same "return raw JSON, retry with a stricter prompt on parse failure" pattern.
