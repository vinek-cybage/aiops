"""
Pulls logs from the `logs` table (see pull_logs.py) and feeds each message
one by one into Drain3, then prints a summary of every cluster.

Modeled on sample_data/drain_tree.py, but reading from the DB instead of
sample_logs.json.

Usage:
  python cluster_logs.py                            # last 20 ERROR logs, any service
  python cluster_logs.py --service orders-service
  python cluster_logs.py --limit 200
"""

import argparse

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from pull_logs import fetch_logs

# ── configure Drain3 (same settings as sample_data/drain_tree.py) ───────────

cfg = TemplateMinerConfig()
cfg.profiling_enabled = False
cfg.drain_sim_th = 0.4
cfg.drain_depth = 4
cfg.drain_max_children = 100

miner = TemplateMiner(config=cfg)


def main():
    parser = argparse.ArgumentParser(description="Cluster DB logs with Drain3.")
    parser.add_argument("--service", help="filter by service, e.g. orders-service")
    parser.add_argument("--level", default="ERROR", help="filter by level (default ERROR)")
    parser.add_argument("--limit", type=int, default=20, help="max rows to pull (default 20)")
    args = parser.parse_args()

    rows = fetch_logs(service=args.service, level=args.level, limit=args.limit)
    rows.reverse()  # oldest first, so clusters form in chronological order

    print(f"Loaded {len(rows)} log entries from the DB\n")
    print("=" * 70)
    print("FEEDING LOGS INTO DRAIN3")
    print("=" * 70)

    for ts, service, level, event, trace_id, message in rows:
        result = miner.add_log_message(message or "")

        status = result.get("change_type", "")
        cid = result.get("cluster_id")
        tmpl = result.get("template_mined", "")

        tag = {
            "none": "  (existing)",
            "cluster_created": "  [NEW CLUSTER]",
            "cluster_template_changed": "  [TEMPLATE UPDATED]",
        }.get(status, f"  [{status}]")

        print(f"[{level:5s}] id={cid:>3}  {service:<20} {(message or '')[:60]}")
        print(f"         template -> {tmpl[:70]}{tag}")
        print()

    # ── print cluster summary ────────────────────────────────────────────────

    clusters = list(miner.drain.id_to_cluster.values())
    clusters.sort(key=lambda c: c.cluster_id)

    print()
    print("=" * 70)
    print(f"CLUSTER SUMMARY  ({len(clusters)} clusters total)")
    print("=" * 70)

    for cl in clusters:
        print(f"\nCluster #{cl.cluster_id}  (size={cl.size})")
        print(f"  Template : {cl.get_template()}")

    print()
    print(f"Total clusters : {len(clusters)}")
    print(f"Total logs fed : {len(rows)}")


if __name__ == "__main__":
    main()
