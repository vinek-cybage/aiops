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

    # Seed default admin user if not present
    cur.execute("""
        INSERT INTO users (name, team_id, role) VALUES ('Admin', NULL, 'admin')
        ON CONFLICT (name) DO NOTHING;
    """)

    conn.commit()
    cur.close(); conn.close()
