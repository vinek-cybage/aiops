"""
Demo runner — single file for all load generation and webhook commands.

Usage:
  python demo.py normal                      # normal traffic only, no faults
  python demo.py fault <name>                # normal traffic + inject a fault
  python demo.py burst <name>                # high-rate burst  (5 journeys/sec)
  python demo.py once <name>                 # fire once and exit (quick test)
  python demo.py webhook <name>              # fire mock alert to AIOps webhook
  python demo.py run <name>                  # fault + webhook together (full demo)
  python demo.py list                        # list all available fault names

Examples:
  python demo.py normal
  python demo.py fault "Payment Gateway Down"
  python demo.py webhook "Payment Gateway Down"
  python demo.py run "Cascade Failure"
  python demo.py burst "DB Pool Exhausted"
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

SCRIPT  = os.path.join(os.path.dirname(__file__), "generate.py")

# Use the venv Python so protobuf==3.20.3 is available (host Python 3.14 crashes with newer protobuf)
_HERE   = os.path.dirname(os.path.abspath(__file__))
_VENV_PY = os.path.join(_HERE, ".venv", "Scripts", "python.exe")
PYTHON  = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable

AIOPS_WEBHOOK = os.getenv("AIOPS_WEBHOOK", "http://localhost:8000/api/webhook/grafana")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


FAULTS = [
    "Payment Gateway Down",
    "Auth / JWT Failures",
    "DB Pool Exhausted",
    "Inventory Race Condition",
    "Cascade Failure",
    "High Latency / SLA Breach",
    "Memory / OOM Pressure",
    "Shipping API Down",
]

# Per-fault mock alert payloads — mirror what Grafana would send
ALERT_PAYLOADS: dict[str, dict] = {
    "Payment Gateway Down": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "Circuit Breaker Open",
                "severity": "critical",
                "app": "demo-service",
                "service_name": "payment-service",
                "alert_type": "metric",
            },
            "annotations": {
                "summary": "Circuit breaker OPEN on payment-service",
                "description": "payment-service circuit breaker tripped after repeated gateway timeouts. All charge requests failing.",
            },
            "startsAt": _now(),
        }],
    },

    "Auth / JWT Failures": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "Auth Failure Spike",
                "severity": "high",
                "app": "demo-service",
                "service_name": "cart-service",
                "alert_type": "log",
            },
            "annotations": {
                "summary": "JWT validation failures spiking on cart-service",
                "description": "High rate of token_expired and signature_mismatch errors from cart-service. Possible token rotation issue or attack.",
            },
            "startsAt": _now(),
        }],
    },

    "DB Pool Exhausted": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "DB Pool Saturated",
                "severity": "critical",
                "app": "demo-service",
                "service_name": "order-service",
                "alert_type": "metric",
            },
            "annotations": {
                "summary": "DB connection pool fully saturated on order-service",
                "description": "order-service DB pool at max_capacity=50 with queries queuing and timing out at 30s.",
            },
            "startsAt": _now(),
        }],
    },

    "Inventory Race Condition": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "Inventory Oversell",
                "severity": "high",
                "app": "demo-service",
                "service_name": "inventory-service",
                "alert_type": "log",
            },
            "annotations": {
                "summary": "Oversell detected — stock going negative on inventory-service",
                "description": "Concurrent reservation requests producing negative stock counts. Compensating transactions required.",
            },
            "startsAt": _now(),
        }],
    },

    "Cascade Failure": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "Circuit Breaker Open",
                "severity": "critical",
                "app": "demo-service",
                "service_name": "payment-service",
                "alert_type": "metric",
            },
            "annotations": {
                "summary": "Circuit breaker OPEN on payment-service causing cascade",
                "description": "payment-service down. order-service connection_refused after 3 retries. cart-service and product-service showing elevated error rates.",
            },
            "startsAt": _now(),
        }],
    },

    "High Latency / SLA Breach": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "High Latency p95",
                "severity": "high",
                "app": "demo-service",
                "service_name": "product-service",
                "alert_type": "metric",
            },
            "annotations": {
                "summary": "p95 latency above 2s SLA threshold on product-service",
                "description": "product-service p99 exceeding 2100-8000ms. Retry storm active. Circuit breaker half-open.",
            },
            "startsAt": _now(),
        }],
    },

    "Memory / OOM Pressure": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "Heap Usage Critical",
                "severity": "high",
                "app": "demo-service",
                "service_name": "order-service",
                "alert_type": "metric",
            },
            "annotations": {
                "summary": "Heap usage critical on order-service — OOM risk",
                "description": "order-service heap above 85%. GC pauses exceeding 1s. OOM imminent on TransactionBatch threads.",
            },
            "startsAt": _now(),
        }],
    },

    "Shipping API Down": {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "Third Party API Down",
                "severity": "high",
                "app": "demo-service",
                "service_name": "notification-service",
                "alert_type": "log",
            },
            "annotations": {
                "summary": "Shipping API unreachable from notification-service",
                "description": "All FedEx webhook deliveries failing after 3 retries. Shipping update notifications not being sent.",
            },
            "startsAt": _now(),
        }],
    },
}


# Patch _now into payloads at call time (not at import time)
def _payload(fault: str) -> dict:
    import copy
    p = copy.deepcopy(ALERT_PAYLOADS[fault])
    for alert in p["alerts"]:
        alert["startsAt"] = _now()
    return p


def fire_webhook(fault: str, wait: int = 15) -> None:
    print(f"\n[webhook] Waiting {wait}s for logs/traces to accumulate in Loki/Tempo...")
    time.sleep(wait)

    payload = json.dumps(_payload(fault)).encode()
    req = urllib.request.Request(
        AIOPS_WEBHOOK,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"[webhook] POST {AIOPS_WEBHOOK}")
    print(f"[webhook] Alert: {_payload(fault)['alerts'][0]['labels']['alertname']} / {fault}")

    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            print(f"[webhook] Response: {resp}")
    except Exception as e:
        print(f"[webhook] ERROR: {e}")
        return

    print(f"\n[webhook] Waiting 35s for LLM to process...")
    time.sleep(35)
    _print_incidents()


def _safe(text: str, limit: int = 0) -> str:
    s = text.encode("ascii", errors="replace").decode("ascii")
    return s[:limit] if limit else s


def _print_incidents():
    try:
        with urllib.request.urlopen("http://localhost:8000/api/incidents", timeout=5) as r:
            incidents = json.loads(r.read())
    except Exception as e:
        print(f"[incidents] Could not fetch: {e}")
        return

    if not incidents:
        print("[incidents] No incidents created yet")
        return

    for inc in incidents:
        print("\n" + "="*60)
        print(f"  {inc['inc_id']} | {_safe(inc['title'])}")
        print(f"  Severity : {inc['severity'].upper()}")
        print(f"  Services : {', '.join(inc['services'])}")
        print(f"  Team     : {inc['team']}")
        print()
        print("  HYPOTHESES:")
        for h in inc["hypotheses"]:
            print(f"    [{h['confidence']}%] {_safe(h['text'])}")
        print()
        print("  EVIDENCE:")
        for e in inc["evidence"]:
            print(f"    [{e['type'].upper()}] {_safe(e['label'])}: {_safe(e['text'], 110)}")
        print()
        print("  SUMMARY:")
        for line in inc["ai_summary"].split(". "):
            if line.strip():
                print(f"    {_safe(line.strip())}.")
        print("="*60)


def _run_generate(extra_args: list[str]):
    env = os.environ.copy()
    env.setdefault("LOKI_URL",      "http://localhost:3100")
    env.setdefault("TEMPO_URL",     "http://localhost:4318")
    env.setdefault("AIOPS_WEBHOOK", "http://localhost:8000/api/webhook/grafana")
    subprocess.run([PYTHON, SCRIPT] + extra_args, env=env)


def usage():
    print(__doc__)
    print("Available faults:")
    for f in FAULTS:
        print(f"  {f}")
    sys.exit(0)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        usage()

    cmd = sys.argv[1].lower()

    if cmd == "list":
        print("Available faults:")
        for f in FAULTS:
            print(f"  {f}")

    elif cmd == "normal":
        print("Starting normal traffic — Ctrl+C to stop")
        _run_generate(["--rate", "2"])

    elif cmd == "fault":
        if len(sys.argv) < 3:
            print("Usage: python demo.py fault \"<fault name>\""); sys.exit(1)
        fault = sys.argv[2]
        if fault not in FAULTS:
            print(f"Unknown fault: '{fault}'"); sys.exit(1)
        print(f"Starting traffic with fault: {fault} — Ctrl+C to stop")
        _run_generate(["--rate", "2", "--fault", fault])

    elif cmd == "burst":
        if len(sys.argv) < 3:
            print("Usage: python demo.py burst \"<fault name>\""); sys.exit(1)
        fault = sys.argv[2]
        if fault not in FAULTS:
            print(f"Unknown fault: '{fault}'"); sys.exit(1)
        print(f"Burst mode — fault: {fault} at 5 journeys/sec — Ctrl+C to stop")
        _run_generate(["--rate", "5", "--fault", fault])

    elif cmd == "once":
        fault = sys.argv[2] if len(sys.argv) > 2 else None
        if fault and fault not in FAULTS:
            print(f"Unknown fault: '{fault}'"); sys.exit(1)
        args = ["--once"]
        if fault:
            args += ["--fault", fault]
            print(f"Single round — fault: {fault}")
        else:
            print("Single round — normal traffic")
        _run_generate(args)

    elif cmd == "webhook":
        if len(sys.argv) < 3:
            print("Usage: python demo.py webhook \"<fault name>\""); sys.exit(1)
        fault = sys.argv[2]
        if fault not in FAULTS:
            print(f"Unknown fault: '{fault}'"); sys.exit(1)
        fire_webhook(fault, wait=0)

    elif cmd == "run":
        # Full demo: start fault as local process, wait for trace-webhook, show incident
        if len(sys.argv) < 3:
            print("Usage: python demo.py run \"<fault name>\""); sys.exit(1)
        fault = sys.argv[2]
        if fault not in FAULTS:
            print(f"Unknown fault: '{fault}'"); sys.exit(1)

        print(f"\n[demo] Starting load generator — fault: {fault}")
        env = os.environ.copy()
        env.setdefault("LOKI_URL",      "http://localhost:3100")
        env.setdefault("TEMPO_URL",     "http://localhost:4318")
        env.setdefault("AIOPS_WEBHOOK", "http://localhost:8000/api/webhook/grafana")

        proc = subprocess.Popen(
            [PYTHON, SCRIPT, "--rate", "2", "--fault", fault],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env,
        )

        print("[demo] Logs flowing (showing first 20 lines):")
        for i, line in enumerate(proc.stdout):
            print(" ", line, end="")
            if i >= 19:
                break

        fire_webhook(fault, wait=10)

        print("\n[demo] Stopping load generator...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    else:
        print(f"Unknown command: '{cmd}'")
        usage()


if __name__ == "__main__":
    main()
