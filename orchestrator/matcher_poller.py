import logging, os

from . import config, db, embeddings, faiss_index, scheduler

logger = logging.getLogger("orchestrator.matcher_poller")


def match_once(action_index):
    conn = db.get_conn()
    try:
        cases = db.fetch_unmatched_cases(conn)
        if not cases:
            return 0

        done = 0
        for case in cases:
            try:
                if len(action_index) == 0:
                    logger.warning("Action index is empty — skipping case %d", case["id"])
                    continue
                text = f"{case['title']} {case['ai_summary']}"
                vector  = embeddings.embed_text(text)
                results = action_index.search(vector, k=min(config.ACTION_MATCH_TOP_K, len(action_index)))
                db.insert_case_actions(conn, case["id"], results)
                db.mark_case_matched(conn, case["id"])
                db.append_case_timeline(conn, case["id"], f"{len(results)} remediation action(s) suggested",
                                         color="#34d399")
                conn.commit()
                logger.info("Case %d matched to %d action(s)", case["id"], len(results))
                done += 1
            except Exception:
                conn.rollback()
                logger.exception("Failed to match case %d — will retry next tick", case["id"])
        return done
    finally:
        conn.close()


def main():
    shared_log_dir = os.getenv("SHARED_LOG_DIR", "/var/log/shared")
    os.makedirs(shared_log_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
                         handlers=[logging.StreamHandler(),
                                   logging.FileHandler(os.path.join(shared_log_dir, "orchestrator-matcher.log"))])
    logger.info("Starting Stage 3 matcher poller")

    db.init_db()

    conn = db.get_conn()
    try:
        action_index = faiss_index.ActionIndex.build_from_db(conn)
    finally:
        conn.close()

    def on_wake():
        try:
            n = match_once(action_index)
            if n:
                logger.info("Matched %d case(s) this cycle", n)
        except Exception:
            logger.exception("match_once failed — will retry next tick")

    scheduler.IntervalTrigger(config.MATCHER_POLL_INTERVAL_SECONDS).run(on_wake)


if __name__ == "__main__":
    main()
