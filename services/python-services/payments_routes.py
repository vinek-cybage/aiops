"""
Payments service — mirrors C# PaymentsController + AdminController.
Rich log messages give Drain3 many distinct templates to cluster.
"""
import asyncio
import random
from pydantic import BaseModel

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import config
from faults import PaymentsFaultState
from instrumentation import LogEvents, LogLevels, RequestFaultContext, write_log

payments_router       = APIRouter(tags=["Payments"])
payments_admin_router = APIRouter(tags=["Payments Admin"])

_GATEWAY_ERRORS = [
    "Connection timeout after 30s",
    "SSL handshake failed",
    "Rate limit exceeded — 429 from provider",
    "Invalid merchant credentials",
    "Gateway returned empty response",
]

_FRAUD_REASONS = [
    "velocity check failed — too many transactions",
    "card BIN flagged as high-risk",
    "billing address mismatch",
    "CVV verification failed",
    "3DS challenge not completed",
]


class ChargeRequest(BaseModel):
    OrderId: int
    Amount:  float


# ── POST /payments/charge ──────────────────────────────────────────────────────
@payments_router.post("/payments/charge", summary="Charge")
async def charge(req: ChargeRequest, request: Request):
    trace_id  = getattr(request.state, "trace_id", None)
    fault_ctx: RequestFaultContext = getattr(request.state, "fault_context", RequestFaultContext())
    provider  = PaymentsFaultState.CurrentPaymentProvider

    await write_log(
        config.PAYMENTS_SERVICE_NAME, LogLevels.INFO, "charge_started", trace_id,
        f"Charge request received order={req.OrderId} amount=${req.Amount} provider={provider} version={PaymentsFaultState.CurrentVersion}",
        {"order_id": req.OrderId, "amount": req.Amount, "provider": provider},
    )

    # ── bad provider (Stripe fault) ──
    if PaymentsFaultState.BadPaymentProvider and provider == "Stripe":
        gateway_err = random.choice(_GATEWAY_ERRORS)
        fault_ctx.set(
            LogEvents.PAYMENT_FAILED,
            f"Payment failed for order {req.OrderId} amount=${req.Amount} provider={provider} error={gateway_err}",
            LogLevels.ERROR,
            {"provider": provider, "order_id": req.OrderId, "amount": req.Amount, "gateway_error": gateway_err},
        )
        await write_log(
            config.PAYMENTS_SERVICE_NAME, LogLevels.ERROR, LogEvents.PAYMENT_FAILED, trace_id,
            f"Stripe gateway error for order {req.OrderId} amount=${req.Amount} — {gateway_err} version={PaymentsFaultState.CurrentVersion}",
            {"order_id": req.OrderId, "amount": req.Amount, "provider": provider, "gateway_error": gateway_err},
        )
        return JSONResponse(
            status_code=503,
            content={"error": "Payment provider unavailable"},
        )

    # ── random fraud check (adds log variety on healthy path) ──
    fraud_roll = random.random()
    if fraud_roll < 0.05:
        reason = random.choice(_FRAUD_REASONS)
        await write_log(
            config.PAYMENTS_SERVICE_NAME, LogLevels.WARN, "fraud_check_warning", trace_id,
            f"Fraud signal detected for order {req.OrderId} amount=${req.Amount} provider={provider} reason={reason} — proceeding version={PaymentsFaultState.CurrentVersion}",
            {"order_id": req.OrderId, "amount": req.Amount, "provider": provider, "fraud_reason": reason},
        )

    # ── simulate provider latency ──
    latency = random.uniform(0.05, 0.15)
    await asyncio.sleep(latency)

    await write_log(
        config.PAYMENTS_SERVICE_NAME, LogLevels.INFO, "charge_authorised", trace_id,
        f"Charge authorised order={req.OrderId} amount=${req.Amount} provider={provider} gateway_ms={round(latency*1000,1)} version={PaymentsFaultState.CurrentVersion}",
        {"order_id": req.OrderId, "amount": req.Amount, "provider": provider, "gateway_ms": round(latency * 1000, 1)},
    )
    return {"status": "success", "provider": provider}


# ── Admin: fault injection ────────────────────────────────────────────────────
@payments_admin_router.post("/admin/payment-provider/stripe", summary="Enable Bad Payment Provider")
async def enable_bad_payment_provider():
    PaymentsFaultState.BadPaymentProvider     = True
    PaymentsFaultState.CurrentPaymentProvider = PaymentsFaultState.StripePaymentProvider
    await write_log(
        config.PAYMENTS_SERVICE_NAME, LogLevels.WARN, "fault_injected", None,
        f"Payment provider switched to Stripe (fault active) — all Stripe charges will fail version={PaymentsFaultState.CurrentVersion}",
        {"fault": "bad_payment_provider", "provider": PaymentsFaultState.CurrentPaymentProvider},
    )
    return {"message": "Bad payment provider enabled.", "provider": PaymentsFaultState.CurrentPaymentProvider}

@payments_admin_router.post("/admin/payment-provider/paypal", summary="Disable Bad Payment Provider")
async def disable_bad_payment_provider():
    PaymentsFaultState.BadPaymentProvider     = False
    PaymentsFaultState.CurrentPaymentProvider = PaymentsFaultState.PaypalPaymentProvider
    await write_log(
        config.PAYMENTS_SERVICE_NAME, LogLevels.INFO, "fault_resolved", None,
        f"Payment provider restored to Paypal — charges resuming normally version={PaymentsFaultState.CurrentVersion}",
        {"fault": "bad_payment_provider", "provider": PaymentsFaultState.CurrentPaymentProvider},
    )
    return {"message": "Bad payment provider disabled.", "provider": PaymentsFaultState.CurrentPaymentProvider}
