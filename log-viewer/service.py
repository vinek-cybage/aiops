"""
Runs forever: every POLL_INTERVAL_SECONDS, pulls any new ERROR logs written
since the last poll and processes each one, oldest first:

  1. Drain3     extract a template (structural clustering)
  2. Embed      Bedrock embedding of the template — only on a brand-new/
                changed Drain3 cluster, cached otherwise
  3. Match      exact Drain3 cluster first (same service only), then cosine
                similarity search restricted to the SAME service — an error
                in payments-service never merges with the "same-looking"
                error in orders-service, they stay separate incidents
  4. Store      new incident, or append this log to the matching incident's
                rolling log window (last 5) — the actual dedup step
  5. Postgres   new incident -> new row in `incidents` (inc_id, services[],
                latest_logs, ...); a match/duplicate -> bump `occurrences`
                and refresh `latest_logs` with the current rolling window
  6. Neo4j      MERGE an Incident node (title/service/status/occurrences/
                sample_logs — no per-log nodes, see neo4j_store.py); a
                genuinely new incident is compared against every other
                (different-service) known incident and gets AT MOST ONE
                RELATED_TO edge to the single strongest match, so the graph
                stays small and easy to read

Usage:
  python service.py
  python service.py --once  # Process once and exit
  python service.py --service orders-service  # Filter by service
"""

import os
import time
import argparse

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

import llm
import neo4j_store
import postgres_store
from embeddings import embed_text, EMBEDDING_DIM
from pull_logs import fetch_new_logs, get_max_id
from vector_store import IncidentStore

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "5"))
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.45"))
PRINT_DRAIN_TREE = os.environ.get("PRINT_DRAIN_TREE", "false").lower() == "true"

cfg = TemplateMinerConfig()
cfg.profiling_enabled = False
cfg.drain_sim_th = 0.4
cfg.drain_depth = 4
cfg.drain_max_children = 100

miner = TemplateMiner(config=cfg)
store = IncidentStore(dim=EMBEDDING_DIM)

# (service, drain_cluster_id) -> incident index — segregated by service so the
# same textual template in two services never collapses into one incident.
cluster_to_incident = {}

_inc_counter = [0]


def _next_inc_id():
    _inc_counter[0] += 1
    return f"INC-{_inc_counter[0]:04d}"


def friendly_title(template):
    """Convert Drain3 template to a readable title."""
    return template.replace("<*>", "…")


def process_log(pg_conn, log_id, ts, service, level, event, trace_id, message):
    message = message or ""
    result = miner.add_log_message(message)
    cid = result["cluster_id"]
    template = result["template_mined"]
    title = friendly_title(template)

    log_entry = {
        "id": log_id, 
        "ts": str(ts), 
        "service": service, 
        "event": event,
        "trace_id": trace_id, 
        "message": message
    }
    key = (service, cid)

    # Layer 1 — exact match: this (service, drain cluster) pair was already mapped to an incident
    if key in cluster_to_incident:
        idx = cluster_to_incident[key]
        store.add_log(idx, log_entry)
        incident = store.get(idx)
        
        postgres_store.update_incident_on_duplicate(pg_conn, incident["incident_id"], log_entry, incident["logs"])
        
        neo4j_store.upsert_service(service)
        neo4j_store.upsert_incident(
            incident["incident_id"], service, log_entry["ts"], title, "open",
            incident["count"], [l["message"] for l in incident["logs"]],
            vector=store.vector_for(idx)
        )
        neo4j_store.link_service_incident(service, incident["incident_id"])
        neo4j_store.upsert_error_pattern(incident["incident_id"], cid, title, log_entry["ts"], message)
        return "DUPLICATE", incident, None

    # Layer 2 — semantic match against known incidents, same service only
    clean = template.replace("<*>", "").strip() or message
    vector = embed_text(clean)
    match = store.search_same_service(vector, SIMILARITY_THRESHOLD, service)
    
    if match:
        idx, score = match
        cluster_to_incident[key] = idx
        store.add_log(idx, log_entry)
        incident = store.get(idx)
        
        postgres_store.update_incident_on_duplicate(pg_conn, incident["incident_id"], log_entry, incident["logs"])
        
        neo4j_store.upsert_service(service)
        neo4j_store.upsert_incident(
            incident["incident_id"], service, log_entry["ts"], title, "open",
            incident["count"], [l["message"] for l in incident["logs"]],
            vector=store.vector_for(idx)
        )
        neo4j_store.link_service_incident(service, incident["incident_id"])
        neo4j_store.upsert_error_pattern(incident["incident_id"], cid, title, log_entry["ts"], message)
        return "SIMILAR", incident, score

    # Layer 3 — genuinely new incident (per service)
    inc_id = _next_inc_id()
    idx = store.add(inc_id, vector, template, service, log_entry)
    cluster_to_incident[key] = idx
    incident = store.get(idx)

    try:
        ai_summary = llm.summarize_incident(title, [service], 1, message)
    except Exception as e:
        print(f"[llm] summary failed: {e}")
        ai_summary = None

    postgres_store.insert_incident(pg_conn, inc_id, title, log_entry, ai_summary=ai_summary)
    
    neo4j_store.upsert_service(service)
    neo4j_store.upsert_incident(
        inc_id, service, log_entry["ts"], title, "open", 1, [message],
        vector=vector
    )
    neo4j_store.link_service_incident(service, inc_id)
    neo4j_store.upsert_error_pattern(inc_id, cid, title, log_entry["ts"], message)
    neo4j_store.link_best_relation(inc_id, service, log_entry["ts"], vector)

    return "NEW", incident, None


def _sync_resolved(pg_conn):
    """Sync resolved incidents from Postgres into the in-memory FAISS store.
    Called every poll cycle so the worker picks up resolutions made via the API."""
    global cluster_to_incident
    cur = pg_conn.cursor()
    cur.execute("SELECT inc_id FROM incidents WHERE status = 'resolved'")
    resolved_ids = {row[0] for row in cur.fetchall()}
    cur.close()
    for idx, inc in enumerate(store.incidents):
        if inc["incident_id"] in resolved_ids and idx not in store._resolved:
            store.resolve(idx)
            cluster_to_incident = {k: v for k, v in cluster_to_incident.items() if v != idx}
            print(f"[resolve] cleared {inc['incident_id']} from FAISS — will reopen as new incident if fault recurs")


def print_incidents():
    print(f"--- {len(store)} incident(s) ---")
    for inc in store.incidents:
        print(f"  {inc['incident_id']}  count={inc['count']:<4} svc={inc['service']:<20} {inc['template']}")
    print()


def print_drain_tree():
    """Dumps Drain3's internal parse tree to stdout."""
    print("--- Drain3 tree ---")
    miner.drain.print_tree()
    print()


def main():
    parser = argparse.ArgumentParser(description="Log processing service for incident detection")
    parser.add_argument("--once", action="store_true", help="Process once and exit")
    parser.add_argument("--service", help="Filter by service name")
    parser.add_argument("--level", default="ERROR", help="Log level to process (default: ERROR)")
    args = parser.parse_args()
    
    last_id = get_max_id()
    print(f"log-viewer service started, polling every {POLL_INTERVAL_SECONDS}s "
          f"(starting after log id={last_id})\n")
    print(f"  Filter: service={args.service or 'all'}, level={args.level}")
    print(f"  Similarity threshold: {SIMILARITY_THRESHOLD}")
    print(f"  Drain3 tree printing: {PRINT_DRAIN_TREE}")
    print()

    neo4j_store.load_existing_incidents()

    pg_conn = postgres_store.get_conn()
    pg_conn.autocommit = True
    _inc_counter[0] = postgres_store.next_inc_id_counter(pg_conn)

    try:
        while True:
            rows = fetch_new_logs(last_id, service=args.service, level=args.level)

            if rows:
                _sync_resolved(pg_conn)
                for log_id, ts, service, level, event, trace_id, message in rows:
                    decision, incident, score = process_log(
                        pg_conn, log_id, ts, service, level, event, trace_id, message
                    )
                    sim = f" sim={score:.2f}" if score is not None else ""
                    print(f"[{ts}] {decision:<9}{sim}  {incident['incident_id']}  svc={service}  {(message or '')[:60]}")
                    last_id = log_id

                print()
                print_incidents()
                if PRINT_DRAIN_TREE:
                    print_drain_tree()
            else:
                print(f"[{time.strftime('%H:%M:%S')}] no new logs (last_id={last_id})")

            if args.once:
                break
                
            time.sleep(POLL_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        pg_conn.close()
        neo4j_store.close()
        print("Service stopped.")


if __name__ == "__main__":
    main()