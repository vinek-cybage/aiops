import json, logging, os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import config, db, dedup, detectors, faiss_index, grouping, scheduler

logger = logging.getLogger("orchestrator.poller")


def poll_once(since_checkpoint, index):
    conn = db.get_conn()
    try:
        now = datetime.now(timezone.utc)

        metrics = db.fetch_new_metrics(conn, since_checkpoint)
        logs    = db.fetch_new_logs(conn, since_checkpoint)
        if not metrics and not logs:
            return since_checkpoint

        new_checkpoint = max([r["ts"] for r in metrics] + [r["ts"] for r in logs])

        breaches = detectors.detect_metric_breaches(metrics)

        rss_lookback_since = now - timedelta(seconds=config.RSS_TREND_LOOKBACK_SECONDS)
        rss_lookback_rows  = db.fetch_new_metrics(conn, rss_lookback_since)
        breaches += detectors.detect_rss_trend_breaches(detectors.group_by_service(rss_lookback_rows))

        breaches += detectors.detect_error_logs(logs)

        if not breaches:
            conn.commit()
            return new_checkpoint

        groups = grouping.group_breaches(breaches, config.GROUPING_WINDOW_SECONDS)

        candidates = db.fetch_recent_open_cases(conn, config.RECURRENCE_LOOKBACK_SECONDS)
        candidates_by_org_service = defaultdict(list)
        for c in candidates:
            candidates_by_org_service[(c["org_id"], c["primary_service"])].append(c)

        # (case_id, vector) pairs for brand-new cases, applied to the FAISS
        # index only after conn.commit() below succeeds — index.add() is an
        # in-memory + on-disk mutation with no rollback, so if any later group
        # in this tick fails and the whole transaction rolls back, an index
        # mutated eagerly here would keep a vector for a case Postgres never
        # actually has (the index is supposed to be a derived, rebuildable
        # cache of Postgres, per CaseIndex's own docstring — not a second
        # source of truth that can drift ahead of it).
        pending_vectors = []

        for group in groups:
            decision = dedup.decide(group, index, candidates_by_org_service.get((group.org_id, group.service), []))
            group_severity = "critical" if any(b.severity == "critical" for b in group.breaches) else "warning"

            if decision.is_duplicate:
                case_id = decision.matched_case_id
                db.update_case_on_duplicate(conn, case_id, similarity_score=decision.score,
                                             occurrence_increment=1, updated_at=now, severity=group_severity)
                db.append_case_timeline(conn, case_id, f"Recurred ({group.service})", color="#fbbf24")
            else:
                case_id = db.insert_case(conn, org_id=group.org_id, status="OPEN", primary_service=group.service,
                                          opened_at=group.first_ts, updated_at=now,
                                          signature_text=decision.signature_text,
                                          similarity_score=decision.score, occurrence_count=1,
                                          severity=group_severity)
                db.append_case_timeline(conn, case_id, "Case opened", color="#818cf8")
                pending_vectors.append((case_id, decision.vector))

            for breach in group.breaches:
                bucket = int(breach.ts.timestamp() // config.GROUPING_WINDOW_SECONDS)
                raw_payload = {
                    "service": breach.service, "metric": breach.metric, "value": breach.value,
                    "ts": breach.ts.isoformat(), "severity": breach.severity,
                    "event": breach.event, "message": breach.message, "trace_id": breach.trace_id,
                }
                db.insert_alert(conn, org_id=group.org_id, case_id=case_id, service=group.service, metric=breach.metric,
                                 severity=breach.severity, triggered_at=breach.ts, received_at=now,
                                 source_tool=config.SOURCE_TOOL_NAME, raw_payload=raw_payload,
                                 dedup_key=f"{group.service}|{breach.metric}|{bucket}")

        conn.commit()

        if pending_vectors:
            for case_id, vector in pending_vectors:
                index.add(case_id, vector)
            index.save()

        return new_checkpoint
    finally:
        conn.close()


def _load_checkpoint():
    if os.path.exists(config.CHECKPOINT_PATH):
        with open(config.CHECKPOINT_PATH) as f:
            return datetime.fromisoformat(json.load(f)["last_ts"])
    conn = db.get_conn()
    try:
        max_ts = db.get_max_seen_ts(conn)
    finally:
        conn.close()
    return max_ts or datetime.now(timezone.utc)


def _save_checkpoint(ts):
    os.makedirs(os.path.dirname(config.CHECKPOINT_PATH), exist_ok=True)
    with open(config.CHECKPOINT_PATH, "w") as f:
        json.dump({"last_ts": ts.isoformat()}, f)


def main():
    shared_log_dir = os.getenv("SHARED_LOG_DIR", "/var/log/shared")
    os.makedirs(shared_log_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
                         handlers=[logging.StreamHandler(),
                                   logging.FileHandler(os.path.join(shared_log_dir, "orchestrator-poller.log"))])
    logger.info("Starting Stage 1 poller")

    db.init_db()

    index = faiss_index.CaseIndex.load_or_create()
    if len(index) == 0:
        conn = db.get_conn()
        try:
            rebuilt = faiss_index.CaseIndex.rebuild_from_db(conn)
        finally:
            conn.close()
        if len(rebuilt) > 0:
            index = rebuilt
            index.save()

    checkpoint = [_load_checkpoint()]
    logger.info("Initial checkpoint: %s | FAISS vectors: %d", checkpoint[0], len(index))

    def on_wake():
        try:
            checkpoint[0] = poll_once(checkpoint[0], index)
            _save_checkpoint(checkpoint[0])
        except Exception:
            logger.exception("poll_once failed — will retry next tick")

    scheduler.IntervalTrigger(config.POLL_INTERVAL_SECONDS).run(on_wake)


if __name__ == "__main__":
    main()
