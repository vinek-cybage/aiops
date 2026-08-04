"""Read-only queries against the Neo4j graph that log-viewer/neo4j_store.py
writes to — Incident nodes + at most one RELATED_TO edge per incident."""

import os

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "aiops123456")

_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_graph():
    with _driver.session() as session:
        nodes = [dict(r["i"]) for r in session.run("MATCH (i:Incident) RETURN i")]
        edges = [
            {
                "source": r["a"]["incident_id"],
                "target": r["b"]["incident_id"],
                "reason": r["r"]["reason"],
                "similarity": r["r"].get("similarity"),
                "seconds_apart": r["r"].get("seconds_apart"),
            }
            for r in session.run("MATCH (a:Incident)-[r:RELATED_TO]->(b:Incident) RETURN a, r, b")
        ]
        return {"nodes": nodes, "edges": edges}
