"""Pull rows from the shared `logs` table (see seed-data.sql) and print them.

Only ERROR-level rows are pulled by default, since those are what matter for
clustering / incident detection.

Usage:
  python pull_logs.py                              # last 20 ERROR log rows, any service
  python pull_logs.py --service orders-service      # filter by service
  python pull_logs.py --level WARN                  # pull a different level
  python pull_logs.py --limit 50
  python pull_logs.py --watch                       # poll every 5s, print first/last id
  python pull_logs.py --watch --interval 10          # custom poll interval
"""

import argparse
import os
import time
from datetime import datetime

import psycopg2

DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_HOST_PORT", "3111")
DB_NAME = os.environ.get("POSTGRES_DB", "aiops")
DB_USER = os.environ.get("POSTGRES_USER", "aiops")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "aiops")


def fetch_logs(service=None, level="ERROR", limit=20):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    try:
        with conn.cursor() as cur:
            where = []
            params = []
            if level:
                where.append("level = %s")
                params.append(level)
            if service:
                where.append("service = %s")
                params.append(service)
            clause = f"WHERE {' AND '.join(where)}" if where else ""
            params.append(limit)
            cur.execute(
                f"""
                SELECT ts, service, level, event, trace_id, message
                FROM logs
                {clause}
                ORDER BY ts DESC
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_max_id():
    """Highest id currently in `logs`, used by service.py to only process new rows."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(id), 0) FROM logs")
            return cur.fetchone()[0]
    finally:
        conn.close()


def get_min_id():
    """Lowest id currently in `logs` — used by --watch to show the current range."""
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MIN(id), 0) FROM logs")
            return cur.fetchone()[0]
    finally:
        conn.close()


def fetch_new_logs(since_id, service=None, level="ERROR"):
    """Rows with id > since_id, oldest first — for continuous polling.
    
    Args:
        since_id: Process logs with ID > this value
        service: Optional service name filter
        level: Log level filter (default: ERROR)
    """
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    try:
        with conn.cursor() as cur:
            where = ["id > %s"]
            params = [since_id]
            if level:
                where.append("level = %s")
                params.append(level)
            if service:
                where.append("service = %s")
                params.append(service)
            cur.execute(
                f"""
                SELECT id, ts, service, level, event, trace_id, message
                FROM logs
                WHERE {' AND '.join(where)}
                ORDER BY id ASC
                """,
                params,
            )
            return cur.fetchall()
    finally:
        conn.close()


def watch(interval=5):
    """Poll the logs table every `interval` seconds, printing the current
    first (MIN) and last (MAX) id, and how many new rows landed since the
    previous check."""
    prev_max = None
    print(f"Watching logs table every {interval}s (Ctrl+C to stop)\n")
    try:
        while True:
            first_id = get_min_id()
            last_id = get_max_id()
            now = datetime.now().strftime("%H:%M:%S")

            new_rows = ""
            if prev_max is not None:
                delta = last_id - prev_max
                new_rows = f"  (+{delta} new)" if delta > 0 else "  (no new rows)"

            print(f"[{now}] first_id={first_id}  last_id={last_id}{new_rows}")

            prev_max = last_id
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def main():
    parser = argparse.ArgumentParser(description="Print recent rows from the logs table.")
    parser.add_argument("--service", help="filter by service, e.g. orders-service")
    parser.add_argument("--level", default="ERROR", help="filter by level (default ERROR)")
    parser.add_argument("--limit", type=int, default=20, help="max rows to print (default 20)")
    parser.add_argument("--watch", action="store_true", help="poll every --interval seconds, printing first/last id")
    parser.add_argument("--interval", type=int, default=5, help="poll interval in seconds for --watch (default 5)")
    args = parser.parse_args()

    if args.watch:
        watch(interval=args.interval)
        return

    rows = fetch_logs(service=args.service, level=args.level, limit=args.limit)

    if not rows:
        print("No logs found.")
        return

    for ts, service, level, event, trace_id, message in rows:
        print(f"[{ts}] {service:<20} {level:<5} {event:<25} trace={trace_id}  {message}")


if __name__ == "__main__":
    main()