from collections import namedtuple, defaultdict

from . import config

# org_id carries the tenant a breach belongs to all the way through
# grouping/dedup/case-creation, so two orgs' data for a same-named service
# (e.g. both onboard a "payments-service") never gets grouped or matched
# together.
Breach = namedtuple("Breach", ["org_id", "service", "metric", "value", "ts", "severity", "event", "message", "trace_id"])


def _severity(value, threshold):
    return "critical" if value > threshold * 2 else "warning"


def group_by_service(rows):
    """Keyed by (org_id, service) — not just service — so tenants never mix."""
    by_org_service = defaultdict(list)
    for row in rows:
        by_org_service[(row["org_id"], row["service"])].append(row)
    return by_org_service


def detect_metric_breaches(rows):
    breaches = []
    for row in rows:
        if row["error_rate"] is not None and row["error_rate"] > config.ERROR_RATE_THRESHOLD:
            breaches.append(Breach(row["org_id"], row["service"], "error_rate", float(row["error_rate"]), row["ts"],
                                    _severity(row["error_rate"], config.ERROR_RATE_THRESHOLD), None, None, None))
        if row["p99_latency_ms"] is not None and row["p99_latency_ms"] > config.LATENCY_THRESHOLD_MS:
            breaches.append(Breach(row["org_id"], row["service"], "p99_latency_ms", float(row["p99_latency_ms"]), row["ts"],
                                    _severity(row["p99_latency_ms"], config.LATENCY_THRESHOLD_MS), None, None, None))
        if row["active_connections"] is not None and row["active_connections"] > config.CONNECTIONS_THRESHOLD:
            breaches.append(Breach(row["org_id"], row["service"], "active_connections", float(row["active_connections"]), row["ts"],
                                    _severity(row["active_connections"], config.CONNECTIONS_THRESHOLD), None, None, None))
    return breaches


def detect_rss_trend_breaches(rows_by_org_service):
    """rss_mb has no fixed threshold (per seed.sql comments) — flag a sustained
    upward slope instead of a single crossed value."""
    breaches = []
    for (org_id, service), rows in rows_by_org_service.items():
        rows = sorted((r for r in rows if r["rss_mb"] is not None), key=lambda r: r["ts"])
        if len(rows) < 4:
            continue
        mid = len(rows) // 2
        first_half, second_half = rows[:mid], rows[mid:]
        first_avg  = sum(float(r["rss_mb"]) for r in first_half) / len(first_half)
        second_avg = sum(float(r["rss_mb"]) for r in second_half) / len(second_half)
        minutes = (second_half[-1]["ts"] - first_half[0]["ts"]).total_seconds() / 60
        if minutes <= 0:
            continue
        slope_mb_per_min = (second_avg - first_avg) / minutes
        if slope_mb_per_min >= config.RSS_TREND_SLOPE_MB_PER_MIN and second_avg >= config.RSS_TREND_MIN_MB:
            breaches.append(Breach(org_id, service, "rss_mb", slope_mb_per_min, second_half[-1]["ts"],
                                    "warning", None, None, None))
    return breaches


def detect_error_logs(rows):
    breaches = []
    for row in rows:
        if row["level"] in ("ERROR", "CRITICAL"):
            breaches.append(Breach(row["org_id"], row["service"], "log_error", 1, row["ts"], "critical",
                                    row["event"], row["message"], row["trace_id"]))
    return breaches
