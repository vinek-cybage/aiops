"""Neo4j graph writes for error incidents.

Graph shape, kept deliberately bounded so it stays readable in the Neo4j
browser even under heavy log volume:

  Service -[:HAS_INCIDENT]-> Incident -[:HAS_ERROR]-> ErrorPattern

  - Service      one node per service name (parent of all its incidents).
  - Incident     one node per unique incident, same as before — no
                 per-log nodes; occurrences/last_seen live as properties.
  - ErrorPattern one node per DISTINCT Drain3 template seen under that
                 incident (keyed by incident_id + drain cluster_id) — NOT
                 one node per raw log line. A recurrence of the same
                 template (Layer 1 exact match in service.py) does not
                 create a new node; it MERGEs onto the existing
                 ErrorPattern and increments its `count` property. A
                 different template that Layer 2 semantic-matches into
                 the same incident gets its own ErrorPattern node — this
                 is rare (most incidents have exactly one), so the graph
                 stays small: growth is in `count`, not in node count.

  - RELATED_TO   at most ONE such relationship is created per new
                 incident (the single strongest related prior incident —
                 same-fault-family semantic match if one clears the
                 threshold, otherwise the closest-in-time cross-service
                 incident) — not one edge per similar/nearby incident
                 found. Never links two incidents from the same service —
                 same-service duplicates are merged into one incident
                 already (see service.py); this relationship only shows
                 how DIFFERENT services' incidents relate to each other.

status stays 'open' on every write here — nothing in this pipeline
resolves an incident; that's expected to happen elsewhere (e.g. the
aiops-api UI), which would SET i.status = 'resolved' directly."""

import os
from datetime import datetime, timezone

import numpy as np
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "aiops123456")

CORR_WINDOW_SECONDS = int(os.environ.get("CORR_WINDOW_SECONDS", "120"))
SAME_FAULT_THRESHOLD = float(os.environ.get("SAME_FAULT_THRESHOLD", "0.45"))

_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

_incident_meta = {}  # incident_id -> {"service", "first_seen" (iso str), "vector"}


def _run(query, **params):
    with _driver.session() as session:
        session.run(query, **params)

def load_existing_incidents():
    """Load all existing incidents from Neo4j to populate _incident_meta."""
    with _driver.session() as session:
        result = session.run("""
            MATCH (i:Incident)
            RETURN i.incident_id AS incident_id, i.service AS service, 
                   i.first_seen AS first_seen, i.vector AS vector
        """)
        for record in result:
            vector = record.get("vector")
            if vector is not None:
                _incident_meta[record["incident_id"]] = {
                    "service": record["service"],
                    "first_seen": record["first_seen"],
                    "vector": np.array(vector, dtype="float32")
                }

def upsert_incident(incident_id, service, ts, title, status, count, sample_logs, vector=None):
    """MERGE so a recurrence just refreshes the same node (last_seen, count,
    sample_logs) instead of creating a duplicate.

    vector is written ONLY on ON CREATE (an incident's embedding is fixed at
    birth) — this is what load_existing_incidents() reads back into
    _incident_meta on restart, so link_best_relation() has history to compare
    against instead of starting empty every time the service restarts."""
    params = dict(incident_id=incident_id, service=service, ts=ts, title=title,
                  status=status, count=count, sample_logs=sample_logs)
    vector_set = ""
    if vector is not None:
        params["vector"] = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        vector_set = "i.vector      = $vector,"
    _run(f"""
        MERGE (i:Incident {{incident_id: $incident_id}})
        ON CREATE SET
            {vector_set}
            i.title       = $title,
            i.service     = $service,
            i.status      = $status,
            i.first_seen  = $ts,
            i.last_seen   = $ts,
            i.occurrences = $count,
            i.sample_logs = $sample_logs
        ON MATCH SET
            i.last_seen   = $ts,
            i.occurrences = $count,
            i.sample_logs = $sample_logs
    """, **params)


def upsert_service(service):
    """MERGE the parent Service node — one per service name, regardless of
    how many incidents it ends up with."""
    _run("MERGE (s:Service {name: $service})", service=service)


def link_service_incident(service, incident_id):
    """MERGE the Service -[:HAS_INCIDENT]-> Incident edge. Safe to call on
    every log for an incident (duplicates and new alike) — MERGE is a no-op
    if the edge already exists."""
    _run("""
        MATCH (s:Service {name: $service})
        MATCH (i:Incident {incident_id: $incident_id})
        MERGE (s)-[:HAS_INCIDENT]->(i)
    """, service=service, incident_id=incident_id)


def upsert_error_pattern(incident_id, cluster_id, title, ts, message):
    """MERGE an ErrorPattern node keyed by (incident_id, drain cluster_id) —
    i.e. one node per distinct template under this incident, never one per
    raw log. First time this (incident, cluster) pair is seen, the node is
    created with count=1. Every later occurrence (a Layer 1 exact-cluster
    duplicate in service.py) hits the same key and just bumps `count` and
    refreshes `last_seen`/`last_message` — no new node, no new edge."""
    pattern_id = f"{incident_id}:{cluster_id}"
    _run("""
        MATCH (i:Incident {incident_id: $incident_id})
        MERGE (e:ErrorPattern {pattern_id: $pattern_id})
        ON CREATE SET
            e.template     = $title,
            e.count        = 1,
            e.first_seen   = $ts,
            e.last_seen    = $ts,
            e.last_message = $message
        ON MATCH SET
            e.count        = e.count + 1,
            e.last_seen    = $ts,
            e.last_message = $message
        MERGE (i)-[:HAS_ERROR]->(e)
    """, incident_id=incident_id, pattern_id=pattern_id, title=title, ts=ts, message=message)


def link_best_relation(new_iid, new_service, new_ts_iso, new_vector):
    """Compares the new incident against every previously known (different-
    service) incident, but writes AT MOST ONE relationship:
      - the strongest SAME_FAULT_FAMILY-style match if its cosine similarity
        clears SAME_FAULT_THRESHOLD, else
      - the closest-in-time incident within CORR_WINDOW_SECONDS, if any.
    Call only for genuinely NEW incidents (not merges)."""
    new_ts = datetime.fromisoformat(str(new_ts_iso))
    if new_ts.tzinfo is None:
        new_ts = new_ts.replace(tzinfo=timezone.utc)

    best_semantic = None   # (iid, similarity)
    best_time = None       # (iid, seconds_apart)

    for iid, meta in _incident_meta.items():
        if meta["service"] == new_service:
            continue

        sim = float(np.dot(new_vector, meta["vector"]))
        if best_semantic is None or sim > best_semantic[1]:
            best_semantic = (iid, sim)

        other_ts = datetime.fromisoformat(meta["first_seen"])
        if other_ts.tzinfo is None:
            other_ts = other_ts.replace(tzinfo=timezone.utc)
        diff = abs((new_ts - other_ts).total_seconds())
        if diff <= CORR_WINDOW_SECONDS and (best_time is None or diff < best_time[1]):
            best_time = (iid, diff)

    if best_semantic and best_semantic[1] >= SAME_FAULT_THRESHOLD:
        other_iid, sim = best_semantic
        seconds_apart = None
        if best_time and best_time[0] == other_iid:
            seconds_apart = round(best_time[1], 1)
        _run("""
            MATCH (a:Incident {incident_id: $new_iid})
            MATCH (b:Incident {incident_id: $other_iid})
            MERGE (a)-[r:RELATED_TO]->(b)
            ON CREATE SET r.reason = 'same_fault_family', r.similarity = $sim, r.seconds_apart = $seconds_apart
        """, new_iid=new_iid, other_iid=other_iid, sim=round(sim, 3), seconds_apart=seconds_apart)
    elif best_time:
        other_iid, diff = best_time
        _run("""
            MATCH (a:Incident {incident_id: $new_iid})
            MATCH (b:Incident {incident_id: $other_iid})
            MERGE (a)-[r:RELATED_TO]->(b)
            ON CREATE SET r.reason = 'correlated_in_time', r.seconds_apart = $diff
        """, new_iid=new_iid, other_iid=other_iid, diff=round(diff, 1))

    _incident_meta[new_iid] = {"service": new_service, "first_seen": str(new_ts_iso), "vector": new_vector}

def resolve_incident(incident_id: str):
    """Mark an incident as resolved in the graph."""
    _run(
        "MATCH (i:Incident {incident_id: $iid}) SET i.status = 'resolved'",
        iid=incident_id,
    )


def close():
    """Close the Neo4j driver connection."""
    _driver.close()