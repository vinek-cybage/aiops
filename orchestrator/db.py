import json
from datetime import datetime, timezone

import psycopg2, psycopg2.extras

from . import config

DATABASE_URL = config.DATABASE_URL


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


# Seed catalog of remediation actions — matched against case ai_summary via
# embedding similarity in matcher_poller.py. One or two per existing load-gen
# fault type (see README.md's fault table for the log messages these map to).
ACTIONS_CATALOG = [
    ("Rollback last deployment", "rollback",
     "Roll back the affected service to its previous deployed version to undo a bad deployment "
     "that is causing cascading failures across dependent services."),
    ("Raise PR: revert suspected bad commit", "raise_pr",
     "Open a pull request reverting the most recent merged change suspected of causing the incident."),
    ("Reset payment gateway circuit breaker", "config_change",
     "The payment gateway circuit breaker is OPEN and blocking all traffic; reset it and re-enable "
     "outbound calls to the payment provider."),
    ("Failover to backup payment provider", "config_change",
     "Payment gateway is unreachable; switch payment processing to the backup provider until the "
     "primary gateway recovers."),
    ("Rotate JWT signing keys", "config_change",
     "JWT validation is failing with expired/invalid tokens; rotate the signing keys and force "
     "re-authentication."),
    ("Block suspicious source IPs", "config_change",
     "Repeated failed authentication attempts from the same IP addresses; add them to the block list."),
    ("Scale database connection pool", "config_change",
     "Database connection pool is exhausted with requests queued and timing out; increase the pool's "
     "max capacity."),
    ("Restart order-service instances", "restart",
     "Restart the affected service's instances to clear a stuck connection pool or memory pressure."),
    ("Run compensating stock-reconciliation job", "restart",
     "Inventory oversell/race condition detected; run the compensating transaction job to reconcile "
     "stock counts."),
    ("Raise PR: add row-level locking for inventory", "raise_pr",
     "Open a pull request adding row-level locking around inventory stock decrements to prevent "
     "concurrent oversell."),
    ("Scale out product-service instances", "config_change",
     "p99 latency has breached SLA with elevated error rates; add more instances to spread load."),
    ("Disable retry-storm amplification", "config_change",
     "Retry storm is amplifying load on an already-degraded service; reduce or disable client retries."),
    ("Raise memory limit and restart pod", "restart",
     "Heap usage is climbing toward an out-of-memory condition; raise the memory limit and restart "
     "the pod."),
    ("Switch to backup shipping provider", "config_change",
     "The primary shipping API is unreachable and webhook deliveries are failing; switch to the "
     "backup shipping provider."),
]


def init_db():
    """Additive-only migrations on top of the seed.sql schema. Never drops or
    re-creates metrics/logs/cases/alerts — that stays the operator's manual step."""
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS signature_text TEXT;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS embedding_id BIGINT;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS duplicate_of BIGINT REFERENCES cases(id);
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS similarity_score NUMERIC(5,4);
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS occurrence_count INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE alerts ADD COLUMN IF NOT EXISTS dedup_key TEXT;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS title TEXT;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS hypotheses JSONB;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS evidence JSONB;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS ai_summary TEXT;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS summarized_at TIMESTAMPTZ;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS severity TEXT;
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]';
        ALTER TABLE cases ADD COLUMN IF NOT EXISTS matched_at TIMESTAMPTZ;

        CREATE TABLE IF NOT EXISTS actions (
            id           SERIAL PRIMARY KEY,
            name         TEXT UNIQUE NOT NULL,
            action_type  TEXT NOT NULL,
            description  TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS case_actions (
            id                SERIAL PRIMARY KEY,
            case_id           BIGINT REFERENCES cases(id),
            action_id         INTEGER REFERENCES actions(id),
            similarity_score  NUMERIC(5,4),
            status            TEXT NOT NULL DEFAULT 'suggested',
            applied_by        TEXT,
            applied_at        TIMESTAMPTZ,
            result            JSONB,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    for name, action_type, description in ACTIONS_CATALOG:
        cur.execute("""
            INSERT INTO actions (name, action_type, description) VALUES (%s, %s, %s)
            ON CONFLICT (name) DO NOTHING
        """, (name, action_type, description))
    conn.commit()
    cur.close(); conn.close()


def fetch_new_metrics(conn, since_ts):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ts, service, error_rate, p99_latency_ms, active_connections, rss_mb, org_id
        FROM metrics WHERE ts > %s ORDER BY ts
    """, (since_ts,))
    rows = cur.fetchall(); cur.close()
    return rows


def fetch_new_logs(conn, since_ts):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ts, service, level, event, trace_id, message, context, org_id
        FROM logs WHERE ts > %s ORDER BY ts
    """, (since_ts,))
    rows = cur.fetchall(); cur.close()
    return rows


def fetch_recent_open_cases(conn, lookback_seconds):
    """Dedup candidates for a service — deliberately includes RESOLVED cases
    (not just OPEN/INVESTIGATING) within the lookback window, so a recurrence
    of an already-resolved case can be matched and reopened by
    update_case_on_duplicate rather than always spawning a new case.
    Returns org_id so the caller can bucket candidates per (org_id, service)
    and never match one tenant's recurrence against another's case."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, status, primary_service, opened_at, updated_at, signature_text, occurrence_count, org_id
        FROM cases
        WHERE updated_at >= NOW() - (%s || ' seconds')::INTERVAL
    """, (lookback_seconds,))
    rows = cur.fetchall(); cur.close()
    return rows


def insert_case(conn, org_id, status, primary_service, opened_at, updated_at, signature_text, similarity_score, occurrence_count, severity):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cases (org_id, status, primary_service, opened_at, updated_at,
                            signature_text, similarity_score, occurrence_count, severity)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (org_id, status, primary_service, opened_at, updated_at, signature_text, similarity_score, occurrence_count, severity))
    case_id = cur.fetchone()["id"]
    cur.execute("UPDATE cases SET embedding_id = %s WHERE id = %s", (case_id, case_id))
    cur.close()
    return case_id


def update_case_on_duplicate(conn, case_id, similarity_score, occurrence_increment, updated_at, severity):
    """Reopening a RESOLVED case (a genuine recurrence) also clears
    summarized_at/matched_at so Stage 2/3 regenerate the summary and
    suggested actions against the new occurrence, instead of leaving stale
    ones from the prior (resolved) occurrence visible in the UI."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE cases
        SET occurrence_count = occurrence_count + %s,
            similarity_score = %s,
            updated_at = %s,
            severity = CASE WHEN %s = 'critical' THEN 'critical' ELSE severity END,
            summarized_at = CASE WHEN status = 'RESOLVED' THEN NULL ELSE summarized_at END,
            matched_at = CASE WHEN status = 'RESOLVED' THEN NULL ELSE matched_at END,
            status = CASE WHEN status = 'RESOLVED' THEN 'INVESTIGATING' ELSE status END
        WHERE id = %s
    """, (occurrence_increment, similarity_score, updated_at, severity, case_id))
    cur.close()


def insert_alert(conn, org_id, case_id, service, metric, severity, triggered_at, received_at,
                  source_tool, raw_payload, dedup_key):
    """Cheap alert-level dedup: if an alert for this exact (case_id, service, metric)
    already exists, bump its duplicate_count instead of inserting a new row. This is
    separate from, and runs before, the FAISS case-level dedup in dedup.py."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM alerts WHERE case_id = %s AND service = %s AND metric = %s
        ORDER BY id DESC LIMIT 1
    """, (case_id, service, metric))
    existing = cur.fetchone()
    if existing:
        cur.execute("""
            UPDATE alerts SET duplicate_count = duplicate_count + 1, received_at = %s
            WHERE id = %s
        """, (received_at, existing["id"]))
    else:
        cur.execute("""
            INSERT INTO alerts (org_id, case_id, source_tool, service, metric, severity,
                                 triggered_at, received_at, duplicate_count, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
        """, (org_id, case_id, source_tool, service, metric, severity, triggered_at, received_at,
              psycopg2.extras.Json(raw_payload)))
    cur.close()


def fetch_unsummarized_cases(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, status, primary_service, opened_at, updated_at,
               signature_text, occurrence_count, similarity_score
        FROM cases
        WHERE summarized_at IS NULL
        ORDER BY opened_at
    """)
    rows = cur.fetchall(); cur.close()
    return rows


def fetch_alerts_for_case(conn, case_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, service, metric, severity, triggered_at, received_at, duplicate_count, raw_payload
        FROM alerts WHERE case_id = %s ORDER BY triggered_at
    """, (case_id,))
    rows = cur.fetchall(); cur.close()
    return rows


def fetch_logs_for_case(conn, service, start_ts, end_ts):
    cur = conn.cursor()
    cur.execute("""
        SELECT ts, level, event, trace_id, message, context
        FROM logs WHERE service = %s AND ts BETWEEN %s AND %s
        ORDER BY ts
    """, (service, start_ts, end_ts))
    rows = cur.fetchall(); cur.close()
    return rows


def save_case_summary(conn, case_id, title, hypotheses, evidence, ai_summary):
    cur = conn.cursor()
    cur.execute("""
        UPDATE cases
        SET title = %s, hypotheses = %s, evidence = %s, ai_summary = %s, summarized_at = NOW()
        WHERE id = %s
    """, (title, psycopg2.extras.Json(hypotheses), psycopg2.extras.Json(evidence), ai_summary, case_id))
    cur.close()


def append_case_timeline(conn, case_id, event, color="#6366f1"):
    cur = conn.cursor()
    entry = json.dumps([{"time": datetime.now(timezone.utc).strftime("%H:%M:%S"), "event": event, "color": color}])
    cur.execute("UPDATE cases SET timeline = timeline || %s::jsonb WHERE id = %s", (entry, case_id))
    cur.close()


def fetch_unmatched_cases(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, status, primary_service, opened_at, updated_at,
               title, ai_summary, occurrence_count, similarity_score
        FROM cases
        WHERE summarized_at IS NOT NULL AND matched_at IS NULL
        ORDER BY opened_at
    """)
    rows = cur.fetchall(); cur.close()
    return rows


def fetch_all_actions(conn):
    cur = conn.cursor()
    cur.execute("SELECT id, name, action_type, description FROM actions ORDER BY id")
    rows = cur.fetchall(); cur.close()
    return rows


def insert_case_actions(conn, case_id, matches):
    """matches: list of (action_id, similarity_score) tuples."""
    cur = conn.cursor()
    for action_id, score in matches:
        cur.execute("""
            INSERT INTO case_actions (case_id, action_id, similarity_score)
            VALUES (%s, %s, %s)
        """, (case_id, action_id, score))
    cur.close()


def mark_case_matched(conn, case_id):
    cur = conn.cursor()
    cur.execute("UPDATE cases SET matched_at = NOW() WHERE id = %s", (case_id,))
    cur.close()


def get_max_seen_ts(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT GREATEST(
            (SELECT MAX(ts) FROM metrics),
            (SELECT MAX(ts) FROM logs)
        ) AS max_ts
    """)
    row = cur.fetchone(); cur.close()
    return row["max_ts"] if row else None
