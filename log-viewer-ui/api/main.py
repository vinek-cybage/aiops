"""Read-only API for the log-viewer incident data — serves the log-viewer-ui
frontend. No auth: internal tool, same trust boundary as log-viewer/aiops-db
themselves (all only reachable inside the compose network / via port-forward)."""

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import db
import graph

try:
    import llm
    _llm_available = True
except Exception as _llm_err:
    print(f"[startup] llm import failed ({_llm_err}) — resolve endpoints disabled")
    _llm_available = False

ORDERS_SERVICE_URL = os.environ.get("ORDERS_SERVICE_URL", "http://orders-service:8081")

app = FastAPI(title="log-viewer-ui API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/incidents")
def api_list_incidents(service: str | None = None, status: str | None = None):
    return db.list_incidents(service=service, status=status)


@app.get("/api/incidents/{inc_id}")
def api_get_incident(inc_id: str):
    incident = db.get_incident(inc_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get("/api/metrics")
def api_metrics():
    return db.dashboard_metrics()


@app.get("/api/graph")
def api_graph():
    return graph.get_graph()


@app.post("/api/incidents/{inc_id}/resolve/preview")
def api_resolve_preview(inc_id: str):
    """Step 1: LLM picks the resolution action. Nothing is executed yet — human must confirm."""
    if not _llm_available:
        raise HTTPException(status_code=503, detail="LLM unavailable — AWS credentials not configured")
    incident = db.get_incident(inc_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident["status"] == "resolved":
        raise HTTPException(status_code=409, detail="Incident is already resolved")

    latest_logs = incident.get("latest_logs") or []
    log_messages = [l["message"] for l in latest_logs]
    log_events   = [l["event"]   for l in latest_logs if l.get("event")]

    try:
        action = llm.choose_resolution_action(
            incident["title"], list(incident["services"]), log_messages, log_events
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    return {"inc_id": inc_id, "action": action}


@app.post("/api/incidents/{inc_id}/resolve/confirm")
def api_resolve_confirm(inc_id: str, action: str):
    """Step 2: Human confirmed. Call orders-service, then mark incident resolved."""
    if action not in [
        "/admin/rollback",
        "/admin/scale-out",
        "/admin/restart-pod",
        "/admin/payment-provider/paypal",
    ]:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    incident = db.get_incident(inc_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident["status"] == "resolved":
        return {"message": "Already resolved", "inc_id": inc_id, "action": action}

    try:
        resp = httpx.post(f"{ORDERS_SERVICE_URL}{action}", timeout=10)
        orders_response = resp.json()
    except Exception as e:
        orders_response = {"error": str(e)}

    db.resolve_incident(inc_id)

    try:
        graph.resolve_incident(inc_id)
    except Exception as e:
        print(f"[neo4j] resolve failed: {e}")

    return {"inc_id": inc_id, "action": action, "orders_response": orders_response}


# Serve the React SPA static build when present (combined container mode).
# In standalone API mode (no static/ dir) the API-only routes above still work.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_STATIC_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        file_candidate = _STATIC_DIR / full_path
        if file_candidate.is_file():
            return FileResponse(str(file_candidate))
        return FileResponse(str(_STATIC_DIR / "index.html"))
