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

-- Shared telemetry tables — written to directly by orders-service /
-- payments-service (via services/instrumentation) and by orchestrator,


CREATE TABLE IF NOT EXISTS metrics (
    id                  BIGSERIAL PRIMARY KEY,
    ts                  TIMESTAMPTZ NOT NULL,
    service             TEXT NOT NULL,
    error_rate          NUMERIC(5,3),
    p99_latency_ms      NUMERIC(8,1),
    active_connections  INTEGER,
    rss_mb              NUMERIC(8,1)
);
CREATE INDEX IF NOT EXISTS idx_metrics_service_ts ON metrics (service, ts);

CREATE TABLE IF NOT EXISTS logs (
    id       BIGSERIAL PRIMARY KEY,
    ts       TIMESTAMPTZ NOT NULL,
    service  TEXT NOT NULL,
    level    TEXT NOT NULL,
    event    TEXT NOT NULL,
    trace_id TEXT,
    message  TEXT,
    context  JSONB
);
CREATE INDEX IF NOT EXISTS idx_logs_service_ts ON logs (service, ts);
CREATE INDEX IF NOT EXISTS idx_logs_trace_id ON logs (trace_id);

CREATE TABLE IF NOT EXISTS traces (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    trace_id    TEXT NOT NULL,
    service     TEXT NOT NULL,
    span_name   TEXT NOT NULL,
    duration_ms NUMERIC(10,2) NOT NULL,
    is_error    BOOLEAN NOT NULL DEFAULT FALSE,
    error_code  TEXT,
    attributes  JSONB
);
CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces (trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_service_ts ON traces (service, ts);