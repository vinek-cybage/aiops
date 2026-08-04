"""
Central config — change any value here to reconfigure the whole app.
"""
import os

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aiops:changeme123@localhost:3111/aiops",
)

# ── Service identity ──────────────────────────────────────────────────────────
ORDERS_SERVICE_NAME    = "orders-service"
PAYMENTS_SERVICE_NAME  = "payments-service"

ORDERS_PORT   = int(os.getenv("ORDERS_SERVICE_PORT", "8081"))

# Both services are combined — payments runs on the same port as orders
PAYMENTS_BASE_URL = os.getenv("PAYMENTS_SERVICE_URL", f"http://localhost:{ORDERS_PORT}")

# ── Fault defaults ────────────────────────────────────────────────────────────
ORDERS_HEALTHY_VERSION = "v126"
ORDERS_FAULTY_VERSION  = "v127"

STRIPE_PROVIDER = "Stripe"
PAYPAL_PROVIDER = "Paypal"

# ── Instrumentation ───────────────────────────────────────────────────────────
METRICS_FLUSH_INTERVAL_SECONDS = 5
DB_MAX_POOL_SIZE = 50

# ── Traffic generator ─────────────────────────────────────────────────────────
TRAFFIC_MIN_DELAY_MS = 300
TRAFFIC_MAX_DELAY_MS = 800
TRAFFIC_CONCURRENT_REQUESTS = 4

# ── Concurrency limiter ───────────────────────────────────────────────────────
MAX_CONCURRENT_REQUESTS = 4

# ── CPU throttle ──────────────────────────────────────────────────────────────
CPU_BUSY_WORK_MS = 500
