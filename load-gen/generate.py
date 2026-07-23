"""
ECommerce load generator — generates structured logs to stdout and fires
AIOps webhook with mock trace context when faults are injected.

Usage:
  python generate.py                              # normal traffic
  python generate.py --fault "Payment Gateway Down"
  python generate.py --list-faults
  python generate.py --once --fault "Cascade Failure"

Environment:
  AIOPS_WEBHOOK  = http://localhost:8000/api/webhook/grafana
"""

import argparse, json, os, random, sys, threading, time
from datetime import datetime, timezone, timedelta

import requests

AIOPS_WEBHOOK = os.getenv("AIOPS_WEBHOOK", "http://localhost:8000/api/webhook/grafana")

SERVICES = [
    "product-service", "cart-service", "order-service",
    "payment-service", "notification-service", "inventory-service",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

_IST = timezone(timedelta(hours=5, minutes=30))

def _ts() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d %H:%M:%S")

def _uid() -> str:
    return f"usr_{random.randint(10000, 99999)}"

def _oid() -> str:
    return f"ord_{random.randint(100000, 999999)}"

def _tid() -> str:
    return f"{random.getrandbits(128):032x}"

def log(service: str, level: str, msg: str, tid: str = "") -> str:
    line = f"{_ts()} {level:<8} [{service}] {msg}"
    if tid:
        line += f" | trace_id={tid}"
    print(line)
    return line

# ── Normal user journeys (INFO logs only, no errors) ──────────────────────────

def run_browse_flow():
    tid     = _tid()
    query   = random.choice(["shoes", "laptop", "headphones", "jacket", "watch"])
    prod_id = random.randint(1000, 9999)
    lat     = random.randint(20, 150)
    log("product-service", "INFO", f'GET /api/products/search | query="{query}" | results={random.randint(10,80)} | latency={lat}ms', tid)
    time.sleep(lat / 1000)
    lat2 = random.randint(15, 80)
    log("product-service", "INFO", f"GET /api/products/{prod_id} | category=electronics | latency={lat2}ms", tid)
    time.sleep(lat2 / 1000)

def run_add_to_cart_flow():
    tid     = _tid()
    uid     = _uid()
    prod_id = random.randint(1000, 9999)
    qty     = random.randint(1, 3)
    log("product-service",   "INFO", f"GET /api/products/{prod_id} | latency={random.randint(10,60)}ms", tid)
    log("cart-service",      "INFO", f"POST /api/cart/add | user={uid} | product={prod_id} | qty={qty} | latency={random.randint(10,50)}ms", tid)
    log("inventory-service", "INFO", f"stock_check | product={prod_id} | available={random.randint(5,200)} | reserved={random.randint(0,10)}", tid)

def run_checkout_flow():
    tid   = _tid()
    uid   = _uid()
    oid   = _oid()
    total = round(random.uniform(29.99, 499.99), 2)
    log("cart-service",         "INFO", f"GET /api/cart | user={uid} | items={random.randint(1,5)} | total={total}", tid)
    log("order-service",        "INFO", f"POST /api/orders | order={oid} | user={uid} | total={total}", tid)
    log("inventory-service",    "INFO", f"reserve_stock | order={oid} | items={random.randint(1,5)}", tid)
    log("payment-service",      "INFO", f"charge | order={oid} | amount={total} | method={random.choice(['credit_card','paypal','apple_pay'])} | status=approved", tid)
    log("notification-service", "INFO", f"send_email | user={uid} | type=order_confirmation | order={oid}", tid)

def run_order_status_flow():
    tid = _tid()
    uid = _uid()
    oid = _oid()
    log("order-service",        "INFO", f"GET /api/orders/{oid} | status=shipped", tid)
    log("notification-service", "INFO", f"push_notification | user={uid} | type=shipment_update", tid)

JOURNEYS = [run_browse_flow, run_add_to_cart_flow, run_checkout_flow, run_order_status_flow]

# ── Fault injectors ────────────────────────────────────────────────────────────
# Each fault:
#   1. Generates realistic ERROR/CRITICAL/WARN log lines to stdout
#   2. Builds a mock trace (span waterfall as text)
#   3. Fires the AIOps webhook with logs + trace embedded in payload

_cooldown: dict[str, float] = {}
_cooldown_lock = threading.Lock()
COOLDOWN_S = 60.0
_webhook_threads: list[threading.Thread] = []

def _should_fire(key: str) -> bool:
    now = time.time()
    with _cooldown_lock:
        if now - _cooldown.get(key, 0) < COOLDOWN_S:
            return False
        _cooldown[key] = now
        return True

def _fire_webhook(alertname: str, severity: str, service: str,
                  tid: str, description: str, logs: list[str], traces: list[str]):
    if not _should_fire(f"{service}:{alertname}"):
        return
    payload = {
        "alerts": [{
            "status":   "firing",
            "labels": {
                "alertname":    alertname,
                "severity":     severity,
                "app":          "demo-service",
                "service_name": service,
                "trace_id":     tid,
                "alert_source": "trace",
            },
            "annotations": {
                "summary":     f"{alertname} on {service}",
                "description": description,
            },
            "startsAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }],
        "context": {"logs": logs, "traces": traces},
    }
    t = threading.Thread(target=_post_webhook, args=(payload, service, tid), daemon=True)
    _webhook_threads.append(t)
    t.start()

def _post_webhook(payload: dict, service: str, tid: str):
    try:
        r = requests.post(AIOPS_WEBHOOK, json=payload, timeout=5)
        print(f"[alert] {service} trace_id={tid} -> webhook {r.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[alert] webhook failed: {e}", file=sys.stderr)


def inject_payment_gateway_down():
    tid   = _tid()
    retry = random.randint(1, 3)
    amt   = round(random.uniform(20, 500), 2)
    logs = [
        log("payment-service", "CRITICAL", f"Gateway unreachable | endpoint=stripe.api | retry=1/3 | circuit_breaker=OPEN", tid),
        log("payment-service", "ERROR",    f"Charge failed | reason=gateway_timeout | amount={amt} | retry=1/3", tid),
        log("payment-service", "CRITICAL", f"Gateway unreachable | endpoint=stripe.api | retry=2/3 | circuit_breaker=OPEN", tid),
        log("payment-service", "ERROR",    f"Charge failed | reason=gateway_timeout | amount={amt} | retry=2/3", tid),
        log("payment-service", "CRITICAL", f"Gateway unreachable | endpoint=stripe.api | retry=3/3 | circuit_breaker=OPEN", tid),
        log("order-service",   "ERROR",    f"checkout_failed | reason=payment_unavailable | circuit_breaker=open", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [payment-service] charge [ERROR] duration=38ms | error=gateway_timeout | payment.amount={amt}",
        f"  [order-service] create_order duration=12ms",
    ]
    _fire_webhook("Circuit Breaker Open", "critical", "payment-service", tid,
                  "payment-service circuit breaker OPEN after stripe.api gateway timeouts", logs, traces)


def inject_auth_jwt_failures():
    tid = _tid()
    ip  = f"10.0.{random.randint(1,254)}.{random.randint(1,254)}"
    attempts = random.randint(20, 100)
    reqs     = random.randint(50, 200)
    logs = [
        log("cart-service", "ERROR",    f"JWT validation failed | reason=token_expired | ip={ip}", tid),
        log("cart-service", "WARN",     f"Rate limiting active | ip={ip} | requests={reqs}/min", tid),
        log("cart-service", "ERROR",    f"JWT validation failed | reason=signature_mismatch | ip={ip}", tid),
        log("cart-service", "CRITICAL", f"Suspicious IP blocked | ip={ip} | failed_attempts={attempts}", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [cart-service] auth_check [ERROR] duration=8ms | error=JWT validation failed | ip={ip}",
    ]
    _fire_webhook("Auth Failure Spike", "high", "cart-service", tid,
                  f"JWT failures from {ip} — {attempts} failed attempts, IP blocked", logs, traces)


def inject_db_pool_exhausted():
    tid     = _tid()
    waiting = random.randint(40, 80)
    logs = [
        log("order-service", "WARN",     f"DB pool pressure | active=50/50 | waiting={waiting}", tid),
        log("order-service", "ERROR",    f"DB pool exhausted | max_capacity=50 | queued={waiting} | timeout=30s", tid),
        log("order-service", "ERROR",    f"Query timeout | query=SELECT_orders | waited=30s", tid),
        log("order-service", "CRITICAL", f"DB connection pool max capacity | queries_failing=true", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [order-service] db_query [ERROR] duration=204ms | error=DB pool exhausted | queued={waiting}",
    ]
    _fire_webhook("DB Pool Saturated", "critical", "order-service", tid,
                  f"order-service DB pool at max_capacity=50, {waiting} queries queuing, SELECT_orders timing out", logs, traces)


def inject_inventory_race():
    tid     = _tid()
    prod_id = random.randint(1000, 9999)
    stock   = random.randint(1, 10)
    conc    = random.randint(2, 8)
    logs = [
        log("inventory-service", "ERROR",    f"Oversell detected | product={prod_id} | stock=-{stock}", tid),
        log("inventory-service", "CRITICAL", f"Stock negative | product={prod_id} | stock=-{stock} | compensating_tx=needed", tid),
        log("inventory-service", "WARN",     f"Race condition | concurrent_reservations={conc} | product={prod_id}", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [inventory-service] reserve_stock [ERROR] duration=22ms | error=Oversell detected | product.id={prod_id} | concurrent={conc}",
    ]
    _fire_webhook("Inventory Oversell", "high", "inventory-service", tid,
                  f"product={prod_id} stock went negative (-{stock}) due to {conc} concurrent reservations", logs, traces)


def inject_cascade_failure():
    tid = _tid()
    logs = [
        log("payment-service", "CRITICAL", f"Service down | all_requests_failing | circuit_breaker=OPEN", tid),
        log("order-service",   "ERROR",    f"payment-service unreachable | connection_refused | retry=3/3", tid),
        log("cart-service",    "ERROR",    f"order-service timeout | downstream_degraded", tid),
        log("product-service", "WARN",     f"Elevated error rate | upstream_failures=cascading | p99=1800ms", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [payment-service] cascade_root [ERROR] duration=41ms | error=Cascade failure",
        f"  [order-service] checkout duration=15ms | downstream=payment-service",
        f"  [cart-service] get_cart duration=9ms",
        f"  [product-service] browse duration=7ms | upstream_errors=cascading",
    ]
    _fire_webhook("Cascade Failure", "critical", "payment-service", tid,
                  "payment-service down, cascade spreading to order → cart → product", logs, traces)


def inject_high_latency():
    tid = _tid()
    p99 = random.randint(2100, 8000)
    retries = random.randint(100, 500)
    logs = [
        log("product-service", "WARN",  f"p99 latency degraded | p99={p99}ms | baseline=120ms | SLA_breach=true", tid),
        log("product-service", "ERROR", f"Request timeout | endpoint=/api/products/search | timeout=30s", tid),
        log("product-service", "ERROR", f"Retry storm | retries={retries}/min | amplification=5x", tid),
        log("product-service", "WARN",  f"Circuit breaker half-open | testing_upstream", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [product-service] search [ERROR] duration={p99}ms | error=p99={p99}ms SLA breach | retries={retries}/min",
    ]
    _fire_webhook("High Latency p95", "high", "product-service", tid,
                  f"product-service p99={p99}ms (baseline 120ms), retry storm at {retries}/min", logs, traces)


def inject_memory_oom():
    tid  = _tid()
    heap = random.randint(85, 98)
    gc   = random.randint(1000, 3000)
    thread_id = random.randint(1, 8)
    logs = [
        log("order-service", "WARN",     f"Heap climbing | used={heap}% | threshold=80% | gc_pause={random.randint(200,800)}ms", tid),
        log("order-service", "ERROR",    f"GC overhead limit exceeded | heap={heap}% | gc_pause={gc}ms", tid),
        log("order-service", "CRITICAL", f"OOM imminent | heap=99% | thread=TransactionBatch-{thread_id}", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [order-service] process_orders [ERROR] duration={gc}ms | error=OOM imminent | heap_pct={heap} | thread=TransactionBatch-{thread_id}",
    ]
    _fire_webhook("Heap Usage Critical", "high", "order-service", tid,
                  f"order-service heap at {heap}%, GC pause {gc}ms, OOM imminent on TransactionBatch-{thread_id}", logs, traces)


def inject_shipping_api_down():
    tid = _tid()
    logs = [
        log("notification-service", "ERROR",    f"Shipping API unreachable | provider=FedEx | timeout=30s", tid),
        log("notification-service", "ERROR",    f"Webhook delivery failed | endpoint=shipping.provider.com | retry=3/3", tid),
        log("notification-service", "CRITICAL", f"All webhook deliveries failing | third_party_down=true", tid),
    ]
    traces = [
        f"TRACE {tid}:",
        f"  [notification-service] send_shipping_update [ERROR] duration=30011ms | error=Shipping API unreachable | provider=FedEx",
    ]
    _fire_webhook("Shipping API Down", "high", "notification-service", tid,
                  "FedEx shipping API unreachable, all webhook deliveries failing after 3 retries", logs, traces)


FAULT_INJECTORS = {
    "Payment Gateway Down":      inject_payment_gateway_down,
    "Auth / JWT Failures":       inject_auth_jwt_failures,
    "DB Pool Exhausted":         inject_db_pool_exhausted,
    "Inventory Race Condition":  inject_inventory_race,
    "Cascade Failure":           inject_cascade_failure,
    "High Latency / SLA Breach": inject_high_latency,
    "Memory / OOM Pressure":     inject_memory_oom,
    "Shipping API Down":         inject_shipping_api_down,
}

# ── Auto loop ──────────────────────────────────────────────────────────────────

_active_faults: set[str] = set()
_rate = 2

def _auto_loop(stop_event: threading.Event):
    tick = 0
    while not stop_event.is_set():
        interval = max(0.1, 1.0 / max(1, _rate))
        try:
            random.choice(JOURNEYS)()
        except Exception as e:
            print(f"[ERROR] journey failed: {e}", file=sys.stderr)
        tick += 1
        if tick % 6 == 0:
            for fault in list(_active_faults):
                try:
                    FAULT_INJECTORS[fault]()
                except Exception:
                    pass
        stop_event.wait(interval)

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ECommerce load generator")
    parser.add_argument("--fault", metavar="NAME", action="append", default=[])
    parser.add_argument("--list-faults", action="store_true")
    parser.add_argument("--rate", type=int, default=2)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if args.list_faults:
        for name in FAULT_INJECTORS:
            print(f"  {name}")
        sys.exit(0)

    global _rate
    _rate = args.rate

    for f in args.fault:
        if f not in FAULT_INJECTORS:
            print(f"[ERROR] Unknown fault: '{f}'", file=sys.stderr); sys.exit(1)
        _active_faults.add(f)

    if _active_faults:
        print(f"Active faults: {', '.join(_active_faults)}")

    if args.once:
        for journey in JOURNEYS:
            try: journey()
            except Exception as e: print(f"[ERROR] {e}", file=sys.stderr)
        for fault in _active_faults:
            try: FAULT_INJECTORS[fault]()
            except Exception as e: print(f"[ERROR] {e}", file=sys.stderr)
        for t in _webhook_threads:
            t.join(timeout=8)
        return

    print(f"Starting load generator — {_rate} journeys/sec. Ctrl+C to stop.")
    stop = threading.Event()
    thread = threading.Thread(target=_auto_loop, args=(stop,), daemon=True)
    thread.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop.set()
        thread.join(timeout=3)
        print("Done.")

if __name__ == "__main__":
    main()
