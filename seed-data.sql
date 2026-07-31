-- ============================================================================
-- seed_db.sql
--
-- PostgreSQL schema + seed data for the AI SRE platform demo.
-- Run this whole file from pgAdmin's Query Tool (or `psql -f seed_db.sql`)
-- against an empty database.
--
-- Safe to re-run: drops and recreates all tables each time, and all
-- timestamps are computed relative to NOW() at execution time, so re-running
-- this always gives you fresh, demo-realistic recent data.
--
-- Seeds:
--   1. Quiet baseline (all 3 services, ~8 min of normal metrics/logs)
--   2. Scenario A: cascading_payment_outage
--      payments-service bad deploy -> payment gateway timeouts
--      -> inventory-service downstream call failures (stock reservation)
--      -> orders-service downstream call failures (checkout)
--      Each of the 6 incident iterations shares ONE trace_id across all
--      three services' logs AND trace spans, so logs and traces correlate
--      both by trace_id and by overlapping timestamps.
--      -> case 1, one alert per affected service (same case)
-- ============================================================================


-- Baseline (all 3 services, same ranges)
-- Metric	Range
-- error_rate	0.0 – 0.02
-- p99_latency_ms	80 – 180
-- active_connections	2 – 6
-- rss_mb	120 – 180
--
-- Incident — payments-service (root cause), cascading to inventory-service
-- and orders-service (downstream symptoms)
-- Metric	Range	Applies to
-- error_rate	0.35 – 0.50 (payments) / 0.20 – 0.35 (inventory, orders)	rows i > 1 (8 of 10 metric rows per service) — first 2 rows stay baseline
-- p99_latency_ms	150 – 250	all 10 incident rows, all 3 services
-- active_connections	3 – 7	all 10 incident rows, all 3 services
-- rss_mb	130 – 160	all 10 incident rows (overlaps baseline upper range — expected, not a signal for this fault)
--
-- thresholds
--error_rate > 0.15
--p99_latency_ms > 800
--active_connections > 18
--rss_mb: trend-based, not a fixed threshold
-- ----------------------------------------------------------------------------
-- 1. SCHEMA
-- ----------------------------------------------------------------------------


DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS cases CASCADE;
DROP TABLE IF EXISTS traces CASCADE;
DROP TABLE IF EXISTS logs CASCADE;
DROP TABLE IF EXISTS metrics CASCADE;

-- Dense time-series, one row per service per sample interval, regardless of fault state
CREATE TABLE metrics (
  id                  BIGSERIAL PRIMARY KEY,
  ts                  TIMESTAMPTZ NOT NULL,
  service             TEXT NOT NULL,
  error_rate          NUMERIC(5,3),
  p99_latency_ms      NUMERIC(8,1),
  active_connections  INTEGER,
  rss_mb              NUMERIC(8,1)
);
CREATE INDEX idx_metrics_service_ts ON metrics (service, ts);

-- Sparse structured events: errors, deploys, downstream call failures, sampled INFO logs
CREATE TABLE logs (
  id            BIGSERIAL PRIMARY KEY,
  ts            TIMESTAMPTZ NOT NULL,
  service       TEXT NOT NULL,
  level         TEXT NOT NULL,          -- INFO | WARN | ERROR
  event         TEXT NOT NULL,          -- e.g. downstream_call_failed, deployment
  trace_id      TEXT,
  message       TEXT,
  context       JSONB
);
CREATE INDEX idx_logs_service_ts ON logs (service, ts);
CREATE INDEX idx_logs_trace_id ON logs (trace_id);

-- Distributed trace spans: one row per service hop, linked by trace_id so a
-- single request's path across payments/inventory/orders can be reconstructed
CREATE TABLE traces (
  id            BIGSERIAL PRIMARY KEY,
  ts            TIMESTAMPTZ NOT NULL,
  trace_id      TEXT NOT NULL,
  service       TEXT NOT NULL,
  span_name     TEXT NOT NULL,
  duration_ms   NUMERIC(10,2) NOT NULL,
  is_error      BOOLEAN NOT NULL DEFAULT FALSE,
  error_code    TEXT,
  attributes    JSONB
);
CREATE INDEX idx_traces_trace_id ON traces (trace_id);
CREATE INDEX idx_traces_service_ts ON traces (service, ts);

CREATE TABLE cases (
  id                BIGSERIAL PRIMARY KEY,
  status            TEXT NOT NULL,      -- OPEN | INVESTIGATING | RESOLVED | ESCALATED
  primary_service   TEXT,
  opened_at         TIMESTAMPTZ,
  updated_at        TIMESTAMPTZ
);

CREATE TABLE alerts (
  id                BIGSERIAL PRIMARY KEY,
  case_id           BIGINT REFERENCES cases(id),
  source_tool       TEXT NOT NULL,      -- e.g. datadog_shaped, prometheus_shaped
  raw_alert_id      TEXT,
  service           TEXT NOT NULL,
  metric            TEXT NOT NULL,
  severity          TEXT,
  triggered_at      TIMESTAMPTZ,
  received_at       TIMESTAMPTZ,
  duplicate_count   INTEGER DEFAULT 1,
  raw_payload       JSONB
);

-- ----------------------------------------------------------------------------
-- 2. SEED DATA
-- ----------------------------------------------------------------------------

DO $$
DECLARE
  services              TEXT[] := ARRAY['payments-service', 'inventory-service', 'orders-service'];
  svc                   TEXT;

  baseline_start        TIMESTAMPTZ := NOW() - INTERVAL '20 minutes';
  scenario_a_start       TIMESTAMPTZ := NOW() - INTERVAL '10 minutes';

  i                      INT;
  t                      TIMESTAMPTZ;

  -- Scenario A vars
  case_a_id              BIGINT;
  deploy_a_log_id        BIGINT;
  trace_id_i             TEXT;

BEGIN

  -- ==========================================================================
  -- 2.1 BASELINE: quiet, continuous metrics for all services, ~8 min, every 2s
  -- ==========================================================================
  FOR i IN 0..239 LOOP
    t := baseline_start + (i * INTERVAL '2 seconds');
    FOREACH svc IN ARRAY services LOOP
      INSERT INTO metrics (ts, service, error_rate, p99_latency_ms, active_connections, rss_mb)
      VALUES (t, svc, round((random() * 0.02)::numeric, 3), round((80 + random() * 100)::numeric, 1),
              (2 + floor(random() * 5))::int, round((120 + random() * 60)::numeric, 1));
    END LOOP;

    IF i % 15 = 0 THEN
      svc := services[1 + floor(random() * 3)::int];
      INSERT INTO logs (ts, service, level, event, trace_id, message, context)
      VALUES (t, svc, 'INFO', 'request_handled', md5(random()::text),
              svc || ' handled request normally', '{}'::jsonb);
    END IF;
  END LOOP;

  -- ==========================================================================
  -- 2.2 SCENARIO A: cascading_payment_outage
  --   payments-service bad deploy -> gateway timeouts
  --   -> inventory-service downstream call failures (stock reservation)
  --   -> orders-service downstream call failures (checkout)
  -- ==========================================================================

  -- deploy event, 6 min before incident window
  INSERT INTO logs (ts, service, level, event, trace_id, message, context)
  VALUES (scenario_a_start - INTERVAL '360 seconds', 'payments-service', 'INFO', 'deployment', NULL,
          'Deployed version v55', jsonb_build_object('version', 'v55', 'previous_version', 'v54'))
  RETURNING id INTO deploy_a_log_id;

  -- 6 correlated incidents: each shares ONE trace_id across all 3 services'
  -- logs AND trace spans, modeling the orders -> inventory -> payments call chain
  FOR i IN 0..5 LOOP
    t := scenario_a_start + (i * 7 * INTERVAL '1 second');
    trace_id_i := md5('cascade-' || i::text || random()::text);

    -- payments-service: root cause error
    INSERT INTO logs (ts, service, level, event, trace_id, message, context)
    VALUES (t, 'payments-service', 'ERROR', 'payment_gateway_timeout', trace_id_i,
            'Timeout calling card processor',
            jsonb_build_object('error_code', 'PAY_504', 'version', 'v55'));

    -- inventory-service: downstream call to payments fails ~2s later
    INSERT INTO logs (ts, service, level, event, trace_id, message, context)
    VALUES (t + INTERVAL '2 seconds', 'inventory-service', 'ERROR', 'downstream_call_failed', trace_id_i,
            'payments-service call timed out during stock reservation',
            jsonb_build_object('error_code', 'INV_502', 'downstream_service', 'payments-service'));

    -- orders-service: checkout fails ~4s later
    INSERT INTO logs (ts, service, level, event, trace_id, message, context)
    VALUES (t + INTERVAL '4 seconds', 'orders-service', 'ERROR', 'checkout_failed', trace_id_i,
            'Unable to complete checkout: inventory reservation failed',
            jsonb_build_object('error_code', 'ORD_500', 'downstream_service', 'inventory-service'));

    -- trace spans for the same trace_id: orders -> inventory -> payments
    INSERT INTO traces (ts, trace_id, service, span_name, duration_ms, is_error, error_code, attributes)
    VALUES (t + INTERVAL '4 seconds', trace_id_i, 'orders-service', 'POST /checkout',
            round((600 + random() * 300)::numeric, 2), TRUE, 'ORD_500',
            jsonb_build_object('http.method', 'POST', 'http.route', '/checkout'));

    INSERT INTO traces (ts, trace_id, service, span_name, duration_ms, is_error, error_code, attributes)
    VALUES (t + INTERVAL '2 seconds', trace_id_i, 'inventory-service', 'reserve_stock',
            round((400 + random() * 200)::numeric, 2), TRUE, 'INV_502',
            jsonb_build_object('downstream_service', 'payments-service'));

    INSERT INTO traces (ts, trace_id, service, span_name, duration_ms, is_error, error_code, attributes)
    VALUES (t, trace_id_i, 'payments-service', 'charge_card',
            round((4800 + random() * 400)::numeric, 2), TRUE, 'PAY_504',
            jsonb_build_object('gateway', 'stripe_shaped'));
  END LOOP;

  -- metrics: error_rate steps up after the first couple of samples, all 3 services
  FOR i IN 0..9 LOOP
    t := scenario_a_start + (i * 5 * INTERVAL '1 second');

    INSERT INTO metrics (ts, service, error_rate, p99_latency_ms, active_connections, rss_mb)
    VALUES (
      t, 'payments-service',
      CASE WHEN i > 1 THEN round((0.35 + random() * 0.15)::numeric, 3)
           ELSE round((random() * 0.02)::numeric, 3) END,
      round((150 + random() * 100)::numeric, 1),
      (3 + floor(random() * 5))::int,
      round((130 + random() * 30)::numeric, 1)
    );

    INSERT INTO metrics (ts, service, error_rate, p99_latency_ms, active_connections, rss_mb)
    VALUES (
      t, 'inventory-service',
      CASE WHEN i > 1 THEN round((0.20 + random() * 0.15)::numeric, 3)
           ELSE round((random() * 0.02)::numeric, 3) END,
      round((150 + random() * 100)::numeric, 1),
      (3 + floor(random() * 5))::int,
      round((130 + random() * 30)::numeric, 1)
    );

    INSERT INTO metrics (ts, service, error_rate, p99_latency_ms, active_connections, rss_mb)
    VALUES (
      t, 'orders-service',
      CASE WHEN i > 1 THEN round((0.20 + random() * 0.15)::numeric, 3)
           ELSE round((random() * 0.02)::numeric, 3) END,
      round((150 + random() * 100)::numeric, 1),
      (3 + floor(random() * 5))::int,
      round((130 + random() * 30)::numeric, 1)
    );
  END LOOP;

  -- case: root cause is payments-service
  INSERT INTO cases (status, primary_service, opened_at, updated_at)
  VALUES ('INVESTIGATING', 'payments-service', scenario_a_start, scenario_a_start + INTERVAL '45 seconds')
  RETURNING id INTO case_a_id;

  -- alerts: one per affected service, same incident
  INSERT INTO alerts (case_id, source_tool, raw_alert_id, service, metric, severity, triggered_at, received_at, raw_payload)
  VALUES (case_a_id, 'datadog_shaped', 'dd-9931', 'payments-service', 'error_rate', 'critical',
          scenario_a_start + INTERVAL '12 seconds', scenario_a_start + INTERVAL '13 seconds',
          jsonb_build_object('alert_id', 'dd-9931', 'title', 'High error rate', 'monitor', 'payments-service.errors'));

  INSERT INTO alerts (case_id, source_tool, raw_alert_id, service, metric, severity, triggered_at, received_at, raw_payload)
  VALUES (case_a_id, 'prometheus_shaped', 'DownstreamCallFailures', 'inventory-service', 'error_rate', 'warning',
          scenario_a_start + INTERVAL '16 seconds', scenario_a_start + INTERVAL '17 seconds',
          jsonb_build_object('alertname', 'DownstreamCallFailures', 'labels', jsonb_build_object('service', 'inventory-service', 'severity', 'warning')));

  INSERT INTO alerts (case_id, source_tool, raw_alert_id, service, metric, severity, triggered_at, received_at, raw_payload)
  VALUES (case_a_id, 'datadog_shaped', 'dd-9932', 'orders-service', 'error_rate', 'critical',
          scenario_a_start + INTERVAL '20 seconds', scenario_a_start + INTERVAL '21 seconds',
          jsonb_build_object('alert_id', 'dd-9932', 'title', 'Checkout failures spiking', 'monitor', 'orders-service.checkout'));

END $$;
-- ----------------------------------------------------------------------------
-- 3. SANITY CHECK (run automatically, shown in pgAdmin's Messages/Output tab)
-- ----------------------------------------------------------------------------
SELECT 'metrics' AS table_name, COUNT(*) AS row_count FROM metrics
UNION ALL SELECT 'logs', COUNT(*) FROM logs
UNION ALL SELECT 'traces', COUNT(*) FROM traces
UNION ALL SELECT 'alerts', COUNT(*) FROM alerts
UNION ALL SELECT 'cases', COUNT(*) FROM cases;
