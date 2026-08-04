"""Read-only queries against the `incidents` table that log-viewer/service.py
writes to (see log-viewer/postgres_store.py for the writer side)."""

import os

import psycopg2
import psycopg2.extras

DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_HOST_PORT", "3111")
DB_NAME = os.environ.get("POSTGRES_DB", "aiops")
DB_USER = os.environ.get("POSTGRES_USER", "aiops")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "aiops")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def list_incidents(service=None, status=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            where = []
            params = []
            if service:
                where.append("%s = ANY(services)")
                params.append(service)
            if status:
                where.append("status = %s")
                params.append(status)
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            cur.execute(f"""
                SELECT inc_id, title, severity, status, services, occurrences,
                       first_seen, last_seen
                FROM incidents
                {clause}
                ORDER BY last_seen DESC
            """, params)
            return cur.fetchall()
    finally:
        conn.close()


def get_incident(inc_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM incidents WHERE inc_id = %s", (inc_id,))
            return cur.fetchone()
    finally:
        conn.close()


def resolve_incident(inc_id: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE incidents SET status = 'resolved', last_seen = NOW() WHERE inc_id = %s",
                (inc_id,)
            )
        conn.commit()
    finally:
        conn.close()


def dashboard_metrics():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM incidents")
            total = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM incidents WHERE status = 'open'")
            open_count = cur.fetchone()["n"]

            cur.execute("SELECT COALESCE(SUM(occurrences), 0) AS n FROM incidents")
            total_occurrences = cur.fetchone()["n"]

            cur.execute("""
                SELECT unnest(services) AS service, COUNT(*) AS incident_count,
                       COALESCE(SUM(occurrences), 0) AS occurrence_count
                FROM incidents
                GROUP BY service
                ORDER BY occurrence_count DESC
            """)
            by_service = cur.fetchall()

            cur.execute("""
                SELECT inc_id, title, services, occurrences, last_seen
                FROM incidents
                ORDER BY last_seen DESC
                LIMIT 5
            """)
            recent = cur.fetchall()

            return {
                "total_incidents": total,
                "open_incidents": open_count,
                "total_occurrences": total_occurrences,
                # every occurrence beyond the first would otherwise have been
                # a brand-new incident without dedup — this is that saving
                "deduped_count": max(total_occurrences - total, 0),
                "by_service": by_service,
                "recent_incidents": recent,
            }
    finally:
        conn.close()
