"""Combined entrypoint that runs all three orchestrator stages (poller,
summarizer, matcher) as threads inside one process/container, instead of
three separate containers.

Trade-off, explicit rather than silent: each stage's own on_wake() already
catches and logs per-tick failures (a bad LLM call, a DB hiccup) and just
retries next tick — that behavior is unchanged. What's lost by merging is
*container-level* crash isolation: if one stage's loop dies from something
its own try/except doesn't catch, the other two threads keep running inside
the same still-alive, still-"healthy" container, with no restart triggered
for the dead stage. main() below watches for exactly that (any stage thread
returning at all, which none of them should ever do under normal operation)
and exits the whole process non-zero so Docker's restart policy brings all
three stages back together, rather than silently limping along on 2/3.

python -m orchestrator.poller / .summarizer_poller / .matcher_poller still
work standalone (e.g. for local debugging one stage in isolation) — this
module doesn't change those, it just composes them.
"""

import logging
import os
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from . import config, db, faiss_index, poller, scheduler
from .matcher_poller import match_once
from .summarizer_poller import summarize_once

logger = logging.getLogger("orchestrator.worker")


def _configure_logging():
    shared_log_dir = os.getenv("SHARED_LOG_DIR", "/var/log/shared")
    os.makedirs(shared_log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    # Keep each stage's own log filename (same ones used when they ran as
    # separate containers) attached to that stage's own named logger, not the
    # root logger — logging.basicConfig() is a one-shot call, so three stages
    # sharing one process would otherwise silently lose two of their three
    # file handlers if each just called basicConfig() the way they do when
    # run standalone.
    for logger_name, filename in [
        ("orchestrator.poller", "orchestrator-poller.log"),
        ("orchestrator.summarizer_poller", "orchestrator-summarizer.log"),
        ("orchestrator.matcher_poller", "orchestrator-matcher.log"),
    ]:
        handler = logging.FileHandler(os.path.join(shared_log_dir, filename))
        handler.setFormatter(fmt)
        logging.getLogger(logger_name).addHandler(handler)


def _run_poller():
    plog = logging.getLogger("orchestrator.poller")
    plog.info("Starting Stage 1 poller")

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

    checkpoint = [poller._load_checkpoint()]
    plog.info("Initial checkpoint: %s | FAISS vectors: %d", checkpoint[0], len(index))

    def on_wake():
        try:
            checkpoint[0] = poller.poll_once(checkpoint[0], index)
            poller._save_checkpoint(checkpoint[0])
        except Exception:
            plog.exception("poll_once failed — will retry next tick")

    scheduler.IntervalTrigger(config.POLL_INTERVAL_SECONDS).run(on_wake)


def _run_summarizer():
    slog = logging.getLogger("orchestrator.summarizer_poller")
    slog.info("Starting Stage 2 summarizer poller")

    def on_wake():
        try:
            n = summarize_once()
            if n:
                slog.info("Summarized %d case(s) this cycle", n)
        except Exception:
            slog.exception("summarize_once failed — will retry next tick")

    scheduler.IntervalTrigger(config.SUMMARIZER_POLL_INTERVAL_SECONDS).run(on_wake)


def _run_matcher():
    mlog = logging.getLogger("orchestrator.matcher_poller")
    mlog.info("Starting Stage 3 matcher poller")

    conn = db.get_conn()
    try:
        action_index = faiss_index.ActionIndex.build_from_db(conn)
    finally:
        conn.close()

    def on_wake():
        try:
            n = match_once(action_index)
            if n:
                mlog.info("Matched %d case(s) this cycle", n)
        except Exception:
            mlog.exception("match_once failed — will retry next tick")

    scheduler.IntervalTrigger(config.MATCHER_POLL_INTERVAL_SECONDS).run(on_wake)


def main():
    _configure_logging()
    logger.info("Starting combined orchestrator worker (poller + summarizer + matcher)")

    db.init_db()

    stages = {"poller": _run_poller, "summarizer": _run_summarizer, "matcher": _run_matcher}
    with ThreadPoolExecutor(max_workers=len(stages)) as pool:
        futures = {pool.submit(fn): name for name, fn in stages.items()}
        done, _pending = wait(futures, return_when=FIRST_COMPLETED)
        for fut in done:
            name = futures[fut]
            exc = fut.exception()
            if exc is not None:
                logger.critical("Stage %r crashed: %r", name, exc)
            else:
                logger.critical("Stage %r returned unexpectedly (it should run forever)", name)
        logger.critical(
            "Exiting the whole process so the container restart policy brings back "
            "all three stages together, instead of silently continuing on 2/3."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
