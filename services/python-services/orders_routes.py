"""
Orders service — mirrors C# OrdersController + AdminController.
Rich log messages give Drain3 many distinct templates to cluster.
"""
import random
import httpx
from fastapi import APIRouter, HTTPException, Request

import config
from faults import ConcurrencyLimitSimulator, CpuThrottleSimulator, OrdersFaultState
from instrumentation import (
    DbConnectionTracker,
    LogEvents,
    LogLevels,
    RequestFaultContext,
    write_log,
)

orders_router = APIRouter(tags=["Orders"])
admin_router  = APIRouter(tags=["Orders Admin"])

db_tracker: DbConnectionTracker = None  # type: ignore

# Realistic customer / product pool for log variety
_CUSTOMERS = ["Alice Johnson", "Bob Martinez", "Carol Lee", "David Kim", "Eva Patel",
               "Frank Chen", "Grace Okonkwo", "Hiro Tanaka", "Isla Scott", "James Nwosu"]
_ITEMS     = ["Laptop Pro 15", "Wireless Headset", "Mechanical Keyboard", "4K Monitor",
               "USB-C Dock", "Ergonomic Chair", "Standing Desk", "Webcam HD",
               "NVMe SSD 1TB", "Gaming Mouse"]
_AMOUNTS   = [49.99, 89.99, 129.99, 199.99, 249.99, 349.99, 499.99, 749.99, 999.99]


def _pick(lst): return lst[random.randint(0, len(lst) - 1)]


# ── GET /orders/{id} ──────────────────────────────────────────────────────────
@orders_router.get("/orders/{id}", summary="Get Order")
async def get_order(id: int, request: Request):
    trace_id  = getattr(request.state, "trace_id", None)
    fault_ctx: RequestFaultContext = getattr(request.state, "fault_context", RequestFaultContext())

    # ── bad deploy ──
    if OrdersFaultState.BadDeployEnabled:
        fault_ctx.set(
            LogEvents.UNHANDLED_EXCEPTION,
            f"TypeError: unsupported operand in pricing calc for order {id} version={OrdersFaultState.CurrentVersion}",
            LogLevels.ERROR,
            {"handler": "get_order", "order_id": id, "version": OrdersFaultState.CurrentVersion},
        )
        raise HTTPException(status_code=500, detail="Internal server error")

    # ── cpu throttle ──
    if CpuThrottleSimulator.Enabled:
        await write_log(
            config.ORDERS_SERVICE_NAME, LogLevels.WARN, "cpu_throttle_active", trace_id,
            f"CPU throttle active for order {id} — busy-waiting {CpuThrottleSimulator.BusyWorkMs}ms version={OrdersFaultState.CurrentVersion}",
            {"order_id": id, "busy_work_ms": CpuThrottleSimulator.BusyWorkMs},
        )
        CpuThrottleSimulator.do_busy_work()

    # ── memory leak ──
    if OrdersFaultState.MemoryLeakEnabled:
        chunk = bytearray(20 * 1024 * 1024)
        for i in range(0, len(chunk), 4096):
            chunk[i] = 1
        OrdersFaultState.LeakedMemory.append(chunk)
        leak_mb = len(OrdersFaultState.LeakedMemory) * 20
        await write_log(
            config.ORDERS_SERVICE_NAME, LogLevels.WARN, "memory_leak_active", trace_id,
            f"Memory leak growing — {leak_mb}MB retained across {len(OrdersFaultState.LeakedMemory)} allocations version={OrdersFaultState.CurrentVersion}",
            {"order_id": id, "leaked_mb": leak_mb, "allocations": len(OrdersFaultState.LeakedMemory)},
        )

    # ── concurrency limit ──
    if ConcurrencyLimitSimulator.Enabled:
        if not ConcurrencyLimitSimulator.try_enter():
            fault_ctx.set(
                LogEvents.RATE_LIMITED,
                f"Concurrency limit reached for order {id} — max={ConcurrencyLimitSimulator.MaxConcurrentRequests} active requests version={OrdersFaultState.CurrentVersion}",
                LogLevels.WARN,
                {"handler": "get_order", "order_id": id, "max_concurrent": ConcurrencyLimitSimulator.MaxConcurrentRequests},
            )
            raise HTTPException(status_code=429)
        try:
            return _order_response(id)
        finally:
            ConcurrencyLimitSimulator.exit()

    # ── db connection leak ──
    if OrdersFaultState.DbConnectionLeakEnabled:
        if db_tracker.active_connections >= DbConnectionTracker.MAX_POOL_SIZE:
            fault_ctx.set(
                LogEvents.DATABASE_CONNECTIONS_EXHAUSTED,
                f"DB pool exhausted — {db_tracker.active_connections}/{DbConnectionTracker.MAX_POOL_SIZE} connections open for order {id} version={OrdersFaultState.CurrentVersion}",
                LogLevels.ERROR,
                {"handler": "get_order", "order_id": id,
                 "active_connections": db_tracker.active_connections,
                 "max_pool_size": DbConnectionTracker.MAX_POOL_SIZE},
            )
            raise HTTPException(status_code=500, detail={"error": "Database unavailable"})
        db_tracker.open()
        await write_log(
            config.ORDERS_SERVICE_NAME, LogLevels.WARN, "db_connection_leak", trace_id,
            f"DB connection opened but not closed for order {id} — {db_tracker.active_connections}/{DbConnectionTracker.MAX_POOL_SIZE} active version={OrdersFaultState.CurrentVersion}",
            {"order_id": id, "active_connections": db_tracker.active_connections},
        )

    return _order_response(id)


def _order_response(order_id: int) -> dict:
    return {
        "orderId":      order_id,
        "customerName": "John Doe",
        "amount":       249.99,
        "status":       "Confirmed",
    }


# ── POST /orders/{id}/checkout ────────────────────────────────────────────────
@orders_router.post("/orders/{id}/checkout", summary="Checkout")
async def checkout(id: int, request: Request):
    trace_id = getattr(request.state, "trace_id", None)
    headers  = {"X-Trace-Id": trace_id} if trace_id else {}
    amount   = _pick(_AMOUNTS)

    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.INFO, "checkout_initiated", trace_id,
        f"Checkout initiated for order {id} amount=${amount} routing to payments-service version={OrdersFaultState.CurrentVersion}",
        {"order_id": id, "amount": amount},
    )

    try:
        async with httpx.AsyncClient(base_url=config.PAYMENTS_BASE_URL) as client:
            resp = await client.post(
                "/payments/charge",
                json={"OrderId": id, "Amount": amount},
                headers=headers,
                timeout=5.0,
            )
            resp.raise_for_status()
            await write_log(
                config.ORDERS_SERVICE_NAME, LogLevels.INFO, "checkout_confirmed", trace_id,
                f"Payment confirmed for order {id} amount=${amount} provider={resp.json().get('provider','unknown')} version={OrdersFaultState.CurrentVersion}",
                {"order_id": id, "amount": amount, "provider": resp.json().get("provider")},
            )
            return {"orderId": id, "status": "confirmed"}
    except httpx.HTTPStatusError as exc:
        await write_log(
            config.ORDERS_SERVICE_NAME, LogLevels.ERROR, LogEvents.HTTP_REQUEST_FAILED, trace_id,
            f"Payment service returned {exc.response.status_code} for order {id} amount=${amount} version={OrdersFaultState.CurrentVersion}",
            {"order_id": id, "amount": amount, "upstream_status": exc.response.status_code},
        )
        raise HTTPException(status_code=502, detail={"error": "Checkout failed: payment processing unavailable"})
    except Exception as exc:
        await write_log(
            config.ORDERS_SERVICE_NAME, LogLevels.ERROR, LogEvents.HTTP_REQUEST_FAILED, trace_id,
            f"Payment service unreachable for order {id} error={type(exc).__name__} version={OrdersFaultState.CurrentVersion}",
            {"order_id": id, "error": type(exc).__name__},
        )
        raise HTTPException(status_code=502, detail={"error": "Checkout failed: payment processing unavailable"})


# ── Admin: fault injection ────────────────────────────────────────────────────
@admin_router.post("/admin/deploy", summary="Deploy")
async def deploy():
    previous = OrdersFaultState.CurrentVersion
    OrdersFaultState.BadDeployEnabled = True
    OrdersFaultState.CurrentVersion   = OrdersFaultState.FaultyVersion
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.INFO, LogEvents.DEPLOYMENT, None,
        f"Deployed version {OrdersFaultState.CurrentVersion} replacing {previous} — bad deploy active",
        {"version": OrdersFaultState.CurrentVersion, "previous_version": previous},
    )
    return {"message": "Deployment completed.", "version": OrdersFaultState.CurrentVersion}

@admin_router.post("/admin/rollback", summary="Rollback")
async def rollback():
    previous = OrdersFaultState.CurrentVersion
    OrdersFaultState.BadDeployEnabled = False
    OrdersFaultState.CurrentVersion   = OrdersFaultState.HealthyVersion
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.INFO, LogEvents.DEPLOYMENT, None,
        f"Rolled back to version {OrdersFaultState.CurrentVersion} from {previous} — service restored",
        {"version": OrdersFaultState.CurrentVersion, "previous_version": previous},
    )
    return {"message": "Rollback completed.", "version": OrdersFaultState.CurrentVersion}

@admin_router.post("/admin/cpu-throttle/on", summary="Cpu Throttle On")
async def cpu_throttle_on():
    CpuThrottleSimulator.Enabled = True
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.WARN, "fault_injected", None,
        f"CPU throttle enabled — {CpuThrottleSimulator.BusyWorkMs}ms busy-wait injected per request version={OrdersFaultState.CurrentVersion}",
        {"fault": "cpu_throttle", "busy_work_ms": CpuThrottleSimulator.BusyWorkMs},
    )
    return {"enabled": True}

@admin_router.post("/admin/concurrency-limit/on", summary="Concurrency Limit On")
async def concurrency_limit_on():
    ConcurrencyLimitSimulator.Enabled = True
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.WARN, "fault_injected", None,
        f"Concurrency limiter enabled — max {ConcurrencyLimitSimulator.MaxConcurrentRequests} concurrent requests version={OrdersFaultState.CurrentVersion}",
        {"fault": "concurrency_limit", "max_concurrent": ConcurrencyLimitSimulator.MaxConcurrentRequests},
    )
    return {"enabled": True}

@admin_router.post("/admin/scale-out", summary="Scale Out")
async def scale_out():
    CpuThrottleSimulator.Enabled      = False
    ConcurrencyLimitSimulator.Enabled = False
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.INFO, "fault_resolved", None,
        f"Scale-out applied — CPU throttle and concurrency limit disabled version={OrdersFaultState.CurrentVersion}",
        {"fault": "scale_out"},
    )
    return {"enabled": False}

@admin_router.post("/admin/memory-leak/on", summary="Memory Leak On")
async def memory_leak_on():
    OrdersFaultState.MemoryLeakEnabled = True
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.WARN, "fault_injected", None,
        f"Memory leak enabled — 20MB allocated per request and retained version={OrdersFaultState.CurrentVersion}",
        {"fault": "memory_leak"},
    )
    return {"enabled": True}

@admin_router.post("/admin/database-connection-leak/on", summary="Db Connection Leak On")
async def db_connection_leak_on():
    OrdersFaultState.DbConnectionLeakEnabled = True
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.WARN, "fault_injected", None,
        f"DB connection leak enabled — connections opened but never closed pool_max={DbConnectionTracker.MAX_POOL_SIZE} version={OrdersFaultState.CurrentVersion}",
        {"fault": "db_connection_leak", "pool_max": DbConnectionTracker.MAX_POOL_SIZE},
    )
    return {"enabled": True}

@admin_router.post("/admin/restart-pod", summary="Restart Pod")
async def restart_pod():
    leaked = len(OrdersFaultState.LeakedMemory)
    conns  = db_tracker.active_connections
    OrdersFaultState.MemoryLeakEnabled       = False
    OrdersFaultState.LeakedMemory.clear()
    OrdersFaultState.DbConnectionLeakEnabled = False
    db_tracker.reset()
    await write_log(
        config.ORDERS_SERVICE_NAME, LogLevels.INFO, "pod_restarted", None,
        f"Pod restarted — cleared {leaked} memory allocations and {conns} leaked DB connections version={OrdersFaultState.CurrentVersion}",
        {"cleared_allocations": leaked, "cleared_connections": conns},
    )
    return {"enabled": False}
