import logging, os
from datetime import timedelta

from . import config, db, llm, scheduler

logger = logging.getLogger("orchestrator.summarizer_poller")


def summarize_once():
    conn = db.get_conn()
    try:
        cases = db.fetch_unsummarized_cases(conn)
        if not cases:
            return 0

        padding = timedelta(seconds=config.CASE_CONTEXT_PADDING_SECONDS)
        done = 0
        for case in cases:
            try:
                alerts = db.fetch_alerts_for_case(conn, case["id"])
                logs   = db.fetch_logs_for_case(conn, case["primary_service"],
                                                 case["opened_at"] - padding, case["updated_at"] + padding)
                result = llm.summarize_case(case, alerts, logs)
                db.save_case_summary(conn, case["id"], result["title"], result["hypotheses"],
                                      result["evidence"], result["ai_summary"])
                db.append_case_timeline(conn, case["id"], "AI summary generated", color="#a78bfa")
                conn.commit()
                logger.info("Case %d summarized: %s", case["id"], result["title"])
                done += 1
            except Exception:
                conn.rollback()
                logger.exception("Failed to summarize case %d — will retry next tick", case["id"])
        return done
    finally:
        conn.close()


def main():
    shared_log_dir = os.getenv("SHARED_LOG_DIR", "/var/log/shared")
    os.makedirs(shared_log_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
                         handlers=[logging.StreamHandler(),
                                   logging.FileHandler(os.path.join(shared_log_dir, "orchestrator-summarizer.log"))])
    logger.info("Starting Stage 2 summarizer poller")

    db.init_db()

    def on_wake():
        try:
            n = summarize_once()
            if n:
                logger.info("Summarized %d case(s) this cycle", n)
        except Exception:
            logger.exception("summarize_once failed — will retry next tick")

    scheduler.IntervalTrigger(config.SUMMARIZER_POLL_INTERVAL_SECONDS).run(on_wake)


if __name__ == "__main__":
    main()
