"""Read-only API for the log-viewer incident data — serves the log-viewer-ui
frontend. No auth: internal tool, same trust boundary as log-viewer/aiops-db
themselves (all only reachable inside the compose network / via port-forward)."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import db
import graph

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
