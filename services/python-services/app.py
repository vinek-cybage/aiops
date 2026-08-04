"""
Combined orders + payments service.
Run with:  uvicorn app:app --host 0.0.0.0 --port 8081
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

import config
import orders_routes
import payments_routes
from orders_routes import orders_router, admin_router as orders_admin_router
from payments_routes import payments_router, payments_admin_router
from faults import OrdersFaultState, PaymentsFaultState
from instrumentation import (
    DbConnectionTracker,
    RequestStats,
    ServiceRoute,
    close_pool,
    make_instrumentation_middleware,
    metrics_flush_loop,
)
from traffic_generator import traffic_loop

# ── Shared state ──────────────────────────────────────────────────────────────
orders_stats   = RequestStats()
payments_stats = RequestStats()
db_tracker     = DbConnectionTracker()

orders_routes.db_tracker = db_tracker


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()

    orders_flush = loop.create_task(
        metrics_flush_loop(
            config.ORDERS_SERVICE_NAME,
            orders_stats,
            db_tracker,
            version_provider=lambda: OrdersFaultState.CurrentVersion,
        )
    )
    payments_flush = loop.create_task(
        metrics_flush_loop(
            config.PAYMENTS_SERVICE_NAME,
            payments_stats,
            db_tracker,
            version_provider=lambda: PaymentsFaultState.CurrentVersion,
        )
    )
    traffic_task = loop.create_task(
        traffic_loop(f"http://localhost:{config.ORDERS_PORT}")
    )

    yield

    orders_flush.cancel()
    payments_flush.cancel()
    traffic_task.cancel()
    await close_pool()


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AIOps Combined Service",
    lifespan=lifespan,
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

app.add_middleware(
    make_instrumentation_middleware([
        ServiceRoute(
            prefix="/payments",
            service_name=config.PAYMENTS_SERVICE_NAME,
            stats=payments_stats,
            version_provider=lambda: PaymentsFaultState.CurrentVersion,
        ),
        ServiceRoute(
            prefix="/orders",
            service_name=config.ORDERS_SERVICE_NAME,
            stats=orders_stats,
            version_provider=lambda: OrdersFaultState.CurrentVersion,
        ),
    ])
)

app.include_router(orders_router)
app.include_router(orders_admin_router)
app.include_router(payments_router)
app.include_router(payments_admin_router)


@app.get("/health", tags=["Health"], summary="Health")
async def health():
    return {
        "orders": {
            "version":               OrdersFaultState.CurrentVersion,
            "bad_deploy":            OrdersFaultState.BadDeployEnabled,
            "memory_leak":           OrdersFaultState.MemoryLeakEnabled,
            "db_leak":               OrdersFaultState.DbConnectionLeakEnabled,
            "active_db_connections": db_tracker.active_connections,
        },
        "payments": {
            "version":          PaymentsFaultState.CurrentVersion,
            "bad_provider":     PaymentsFaultState.BadPaymentProvider,
            "current_provider": PaymentsFaultState.CurrentPaymentProvider,
        },
    }
