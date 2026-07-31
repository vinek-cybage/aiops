import os, psycopg2, psycopg2.extras

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/aiops")

def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_conn()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id       SERIAL PRIMARY KEY,
            name     TEXT UNIQUE NOT NULL,
            services TEXT[] NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS users (
            id      SERIAL PRIMARY KEY,
            name    TEXT UNIQUE NOT NULL,
            team_id INT REFERENCES teams(id) ON DELETE SET NULL,
            role    TEXT NOT NULL DEFAULT 'member'
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id          SERIAL PRIMARY KEY,
            inc_id      TEXT UNIQUE NOT NULL,
            title       TEXT NOT NULL,
            severity    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'open',
            services    TEXT[],
            team        TEXT,
            hypotheses  JSONB,
            evidence    JSONB,
            timeline    JSONB,
            ai_summary  TEXT,
            occurrences INT NOT NULL DEFAULT 1,
            cascades    JSONB NOT NULL DEFAULT '[]',
            first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            latest_logs JSONB
        );
    """)

    for col, defn in [("cascades", "JSONB NOT NULL DEFAULT '[]'"), ("occurrences", "INT NOT NULL DEFAULT 1")]:
        cur.execute(f"ALTER TABLE incidents ADD COLUMN IF NOT EXISTS {col} {defn};")
    for col in ("duplicate_of", "cascade_of"):
        cur.execute(f"ALTER TABLE incidents DROP COLUMN IF EXISTS {col};")

    # NOTE: the default-admin seed insert that used to live here has moved —
    # organizations/users now carry auth columns (org_id/email/password_hash)
    # owned by the Alembic migrations in alembic/versions/, which also seed the
    # "Default Org" tenant. The first real admin account is created via
    # POST /api/auth/register instead of a hardcoded seed row.

    conn.commit()
    cur.close(); conn.close()


# ── shared telemetry tables (owned/written by telemetry-api, same DB) ──────────
# These tables (metrics, logs, cases, alerts) aren't created here — telemetry-api
# creates them on startup. Queries are read-only and fail soft if the tables
# aren't there yet (e.g. telemetry-api hasn't started for the first time).

def get_recent_logs(service: str | None = None, limit: int = 20) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT ts, service, level, event, trace_id, message, context
        FROM logs
        WHERE %(service)s IS NULL OR service = %(service)s
        ORDER BY ts DESC LIMIT %(limit)s
    """, {"service": service, "limit": limit})
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def get_recent_metrics(service: str | None = None, limit: int = 20) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT ts, service, error_rate, p99_latency_ms, active_connections, rss_mb
        FROM metrics
        WHERE %(service)s IS NULL OR service = %(service)s
        ORDER BY ts DESC LIMIT %(limit)s
    """, {"service": service, "limit": limit})
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def get_open_cases_for_service(service: str | None = None, limit: int = 5) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.status, c.primary_service, c.opened_at, c.updated_at,
               COALESCE(json_agg(json_build_object(
                   'source_tool', a.source_tool, 'metric', a.metric,
                   'severity', a.severity, 'triggered_at', a.triggered_at
               )) FILTER (WHERE a.id IS NOT NULL), '[]') AS alerts
        FROM cases c
        LEFT JOIN alerts a ON a.case_id = c.id
        WHERE c.status != 'RESOLVED' AND (%(service)s IS NULL OR c.primary_service = %(service)s)
        GROUP BY c.id
        ORDER BY c.opened_at DESC LIMIT %(limit)s
    """, {"service": service, "limit": limit})
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows
