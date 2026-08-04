"""
Shared instrumentation: structured logging to DB, metrics flushing, trace-id middleware.
Faithfully mirrors the C# instrumentation library.
"""
import asyncio
import json
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import asyncpg
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import config

# ── Constants ─────────────────────────────────────────────────────────────────
TRACE_ID_HEADER = "X-Trace-Id"

class LogEvents:
    REQUEST_HANDLED                = "request_handled"
    UNHANDLED_EXCEPTION            = "unhandled_exception"
    DEPLOYMENT                     = "deployment"
    HTTP_REQUEST_FAILED            = "http_request_failed"
    RATE_LIMITED                   = "rate_limited"
    PAYMENT_FAILED                 = "payment_failed"
    DATABASE_CONNECTIONS_EXHAUSTED = "database_connections_exhausted"

class LogLevels:
    INFO  = "INFO"
    WARN  = "WARN"
    ERROR = "ERROR"


# ── RequestFaultContext (scoped per request, mirrors C# scoped service) ───────
class RequestFaultContext:
    """Populated by business logic; read by middleware when writing failure logs."""

    def __init__(self):
        self.event:      Optional[str] = None
        self.message:    Optional[str] = None
        self.level:      Optional[str] = None
        self.properties: dict          = {}

    def set(self, event: str, message: str, level: str, properties: dict):
        self.event   = event
        self.message = message
        self.level   = level
        self.properties.update(properties)


# ── DB pool ───────────────────────────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=2, max_size=10)
        except Exception as exc:
            raise ConnectionError(f"DB unavailable: {exc}") from exc
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Log writer (mirrors LogWriter.WriteAsync) ─────────────────────────────────
async def write_log(
    service: str,
    level: str,
    event: str,
    trace_id: Optional[str],
    message: str,
    context: Optional[dict] = None,
):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO logs (ts, service, level, event, trace_id, message, context)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                datetime.now(timezone.utc),
                service,
                level,
                event,
                trace_id,
                message,
                json.dumps(context) if context else None,
            )
    except Exception:
        print(f"[{level}] {service} | {event} | trace={trace_id} | {message}")


# ── Request stats (mirrors RequestStats) ──────────────────────────────────────
class RequestStats:
    def __init__(self):
        self._lock      = asyncio.Lock()
        self._total     = 0
        self._failed    = 0
        self._latencies: list = []

    async def record(self, success: bool, latency_ms: float):
        async with self._lock:
            self._total += 1
            if not success:
                self._failed += 1
            self._latencies.append(latency_ms)

    async def take_snapshot_and_reset(self) -> dict:
        async with self._lock:
            total   = self._total
            failed  = self._failed
            lats    = list(self._latencies)
            self._total    = 0
            self._failed   = 0
            self._latencies.clear()

        lats.sort()
        p99 = 0.0
        if lats:
            idx = max(0, min(int(len(lats) * 0.99 + 0.9999) - 1, len(lats) - 1))
            p99 = lats[idx]

        error_rate = (failed / total) if total else 0.0
        return {"total": total, "failed": failed, "error_rate": error_rate, "p99_ms": p99}


# ── DB connection tracker (mirrors DbConnectionTracker) ───────────────────────
class DbConnectionTracker:
    def __init__(self):
        self._active = 0

    MAX_POOL_SIZE = 50

    @property
    def active_connections(self): return self._active
    def open(self):   self._active += 1
    def close(self):  self._active -= 1
    def reset(self):  self._active = 0


# ── Metrics flush loop (mirrors MetricsCollector BackgroundService) ───────────
async def metrics_flush_loop(
    service_name: str,
    stats: RequestStats,
    tracker: DbConnectionTracker,
    version_provider: Optional[Callable[[], str]] = None,
):
    import psutil, os
    while True:
        await asyncio.sleep(config.METRICS_FLUSH_INTERVAL_SECONDS)
        snap = await stats.take_snapshot_and_reset()
        try:
            rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        except Exception:
            rss_mb = 0.0
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO metrics
                        (ts, service, error_rate, p99_latency_ms, active_connections, rss_mb)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    datetime.now(timezone.utc),
                    service_name,
                    snap["error_rate"],
                    snap["p99_ms"],
                    tracker.active_connections,
                    rss_mb,
                )
        except Exception:
            pass


# ── Helper: snake_case (mirrors InstrumentationMiddleware.ToSnakeCase) ────────
def _to_snake_case(name: str) -> str:
    result = []
    for i, ch in enumerate(name):
        if i > 0 and ch.isupper():
            result.append(f"_{ch.lower()}")
        else:
            result.append(ch.lower())
    return "".join(result)


# ── Service routing config (used by middleware to pick service per path) ───────
class ServiceRoute:
    """Binds a URL prefix to a service name, its stats bucket, and version fn."""
    def __init__(
        self,
        prefix: str,
        service_name: str,
        stats: "RequestStats",
        version_provider: Optional[Callable[[], str]] = None,
    ):
        self.prefix           = prefix
        self.service_name     = service_name
        self.stats            = stats
        self.version_provider = version_provider


# ── Middleware factory (path-aware — resolves service per request) ─────────────
def make_instrumentation_middleware(routes: list):
    """
    routes: list of ServiceRoute, checked in order — first prefix match wins.
    Requests that match no route (e.g. /health) are passed through untracked.
    """
    class InstrumentationMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            if request.url.path.startswith("/admin"):
                return await call_next(request)

            # Resolve which logical service owns this request
            route: Optional[ServiceRoute] = None
            for r in routes:
                if request.url.path.startswith(r.prefix):
                    route = r
                    break

            if route is None:
                return await call_next(request)

            service_name     = route.service_name
            stats            = route.stats
            version_provider = route.version_provider

            fault_ctx = RequestFaultContext()
            request.state.fault_context = fault_ctx

            trace_id = request.headers.get(TRACE_ID_HEADER) or uuid.uuid4().hex
            request.state.trace_id = trace_id

            import time as _time
            start       = _time.perf_counter()
            success     = False
            status_code = 500

            try:
                response    = await call_next(request)
                status_code = response.status_code
                success     = status_code < 500
            except Exception as exc:
                latency_ms = (_time.perf_counter() - start) * 1000
                await stats.record(False, latency_ms)
                await _write_failure_log(
                    service_name, request, fault_ctx, trace_id,
                    latency_ms, status_code, version_provider,
                    fallback_message=str(exc),
                )
                raise

            latency_ms = (_time.perf_counter() - start) * 1000
            await stats.record(success, latency_ms)

            handler = _get_handler(request)
            version = version_provider() if version_provider else None

            if not success or status_code >= 400:
                await _write_failure_log(
                    service_name, request, fault_ctx, trace_id,
                    latency_ms, status_code, version_provider, handler, version,
                )
            else:
                message = _success_message(handler, request, status_code, latency_ms, version)
                await write_log(
                    service_name, LogLevels.INFO, LogEvents.REQUEST_HANDLED, trace_id,
                    message,
                    {
                        "handler":     handler,
                        "version":     version,
                        "method":      request.method,
                        "path":        request.url.path,
                        "status_code": status_code,
                        "latency_ms":  round(latency_ms, 4),
                    },
                )

            response.headers[TRACE_ID_HEADER] = trace_id
            return response

    return InstrumentationMiddleware


def _success_message(handler: str, request: Request, status_code: int, latency_ms: float, version: Optional[str]) -> str:
    path = request.url.path
    method = request.method
    ms = round(latency_ms, 2)
    v = version or "unknown"

    templates = {
        "get_order":                    f"GET order {path} returned {status_code} in {ms}ms version={v}",
        "checkout":                     f"POST checkout {path} payment accepted status={status_code} latency={ms}ms version={v}",
        "charge":                       f"POST payments/charge processed status={status_code} latency={ms}ms version={v}",
        "enable_bad_payment_provider":  f"Payment provider switched to Stripe (fault enabled) version={v}",
        "disable_bad_payment_provider": f"Payment provider switched to Paypal (fault disabled) version={v}",
    }
    return templates.get(handler, f"{method} {path} completed status={status_code} latency={ms}ms version={v}")


async def _write_failure_log(
    service_name: str,
    request: Request,
    fault_ctx: RequestFaultContext,
    trace_id: str,
    latency_ms: float,
    status_code: int,
    version_provider: Optional[Callable[[], str]],
    handler: str,
    version: Optional[str],
):
    path   = request.url.path
    method = request.method
    ms     = round(latency_ms, 2)
    v      = version or "unknown"
    sc     = status_code if status_code >= 400 else 500

    failure_templates = {
        "get_order": f"GET order {path} failed status={sc} latency={ms}ms version={v}",
        "checkout":  f"POST checkout {path} payment failed status={sc} latency={ms}ms version={v}",
        "charge":    f"POST payments/charge failed status={sc} latency={ms}ms version={v}",
    }
    fallback = failure_templates.get(handler, f"{method} {path} error status={sc} latency={ms}ms version={v}")

    log_context = dict(fault_ctx.properties)
    log_context.update({
        "handler":     handler,
        "version":     version,
        "path":        path,
        "method":      method,
        "status_code": sc,
        "latency_ms":  ms,
    })

    await write_log(
        service_name,
        fault_ctx.level   or LogLevels.ERROR,
        fault_ctx.event   or LogEvents.HTTP_REQUEST_FAILED,
        trace_id,
        fault_ctx.message or fallback,
        log_context,
    )


def _get_handler(request: Request) -> str:
    endpoint = request.scope.get("endpoint")
    if endpoint and hasattr(endpoint, "__name__"):
        return _to_snake_case(endpoint.__name__)
    return "unknown"
