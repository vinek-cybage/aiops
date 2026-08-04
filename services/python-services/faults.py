"""
Fault state for both services — exact mirror of C# FaultState, CpuThrottleSimulator,
ConcurrencyLimitSimulator classes.
"""
import threading
import time

import config


# ── Orders FaultState ─────────────────────────────────────────────────────────
class OrdersFaultState:
    BadDeployEnabled      = False
    HealthyVersion        = config.ORDERS_HEALTHY_VERSION
    FaultyVersion         = config.ORDERS_FAULTY_VERSION
    CurrentVersion        = config.ORDERS_HEALTHY_VERSION
    MemoryLeakEnabled     = False
    LeakedMemory: list    = []
    DbConnectionLeakEnabled = False


# ── CpuThrottleSimulator ──────────────────────────────────────────────────────
class CpuThrottleSimulator:
    Enabled     = False
    BusyWorkMs  = config.CPU_BUSY_WORK_MS

    @classmethod
    def do_busy_work(cls):
        deadline = time.perf_counter() + cls.BusyWorkMs / 1000.0
        while time.perf_counter() < deadline:
            pass  # spin-wait, mirrors Thread.SpinWait


# ── ConcurrencyLimitSimulator ─────────────────────────────────────────────────
class ConcurrencyLimitSimulator:
    Enabled              = False
    MaxConcurrentRequests = config.MAX_CONCURRENT_REQUESTS
    _lock                = threading.Lock()
    _concurrent_requests = 0

    @classmethod
    def try_enter(cls) -> bool:
        with cls._lock:
            cls._concurrent_requests += 1
            if cls._concurrent_requests <= cls.MaxConcurrentRequests:
                return True
            cls._concurrent_requests -= 1
            return False

    @classmethod
    def exit(cls):
        with cls._lock:
            if cls._concurrent_requests > 0:
                cls._concurrent_requests -= 1


# ── Payments FaultState ───────────────────────────────────────────────────────
class PaymentsFaultState:
    StripePaymentProvider  = config.STRIPE_PROVIDER
    PaypalPaymentProvider  = config.PAYPAL_PROVIDER
    CurrentPaymentProvider = config.PAYPAL_PROVIDER   # default: Paypal (healthy)
    BadPaymentProvider     = False
    CurrentVersion         = "1.0.0"
