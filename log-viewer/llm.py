"""Bedrock Claude text generation — incident summarization and resolution routing."""

import os

import boto3

AWS_PROFILE = os.environ.get("AWS_PROFILE")
AWS_REGION  = os.environ.get("AWS_REGION", "us-west-2")
MODEL_ID    = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")

_session = boto3.Session(profile_name=AWS_PROFILE) if AWS_PROFILE else boto3.Session()
_bedrock = _session.client("bedrock-runtime", region_name=AWS_REGION)

_RESOLUTION_ENDPOINTS = [
    "/admin/rollback",
    "/admin/scale-out",
    "/admin/restart-pod",
    "/admin/payment-provider/paypal",
]

# Full fault→resolution mapping with exact log events and sample messages from the orders-service.
# This gives the LLM enough signal to match even when Drain3 has templated away variable parts.
_FAULT_KNOWLEDGE = """
FAULT KNOWLEDGE BASE — orders-service faults and their resolution endpoints:

1. BAD DEPLOY → POST /admin/rollback
   Log events: unhandled_exception, deployment
   Sample logs:
     - "TypeError: unsupported operand in pricing calc for order <N> version=v127"
     - "Deployed version v127 replacing v126 — bad deploy active"
   Signs: TypeError / unhandled_exception errors tied to a version number, HTTP 500s

2. CPU THROTTLE → POST /admin/scale-out
   Log events: cpu_throttle_active, fault_injected
   Sample logs:
     - "CPU throttle active for order <N> — busy-waiting 500ms version=v126"
     - "CPU throttle enabled — 500ms busy-wait injected per request version=v126"
   Signs: busy-wait language, high latency, cpu_throttle_active events

3. CONCURRENCY LIMIT → POST /admin/scale-out
   Log events: rate_limited, fault_injected
   Sample logs:
     - "Concurrency limit reached for order <N> — max=4 active requests version=v126"
     - "Concurrency limiter enabled — max 4 concurrent requests version=v126"
   Signs: rate_limited events, max=N active requests, HTTP 429s

4. MEMORY LEAK → POST /admin/restart-pod
   Log events: memory_leak_active, fault_injected
   Sample logs:
     - "Memory leak growing — 160MB retained across 8 allocations version=v126"
     - "Memory leak enabled — 20MB allocated per request and retained version=v126"
   Signs: MB retained, allocations growing, memory_leak_active events

5. DB CONNECTION LEAK → POST /admin/restart-pod
   Log events: db_connection_leak, database_connections_exhausted, fault_injected
   Sample logs:
     - "DB connection opened but not closed for order <N> — 3/50 active version=v126"
     - "DB pool exhausted — 50/50 connections open for order <N> version=v126"
     - "DB connection leak enabled — connections opened but never closed pool_max=50"
   Signs: connection leak language, pool exhausted, db_connection_leak events

6. BAD PAYMENT PROVIDER (Stripe) → POST /admin/payment-provider/paypal
   Log events: payment_failed, fault_injected
   Sample logs:
     - "Stripe gateway error for order <N> amount=$49.99 — Gateway returned empty response"
     - "Payment provider switched to Stripe (fault active) — all Stripe charges will fail"
   Signs: Stripe errors, payment_failed events, gateway empty response
"""


def choose_resolution_action(title: str, services: list, log_messages: list, log_events: list = None) -> str:
    logs_text = "\n".join(f"  - {m}" for m in log_messages[:10])
    events_text = ", ".join(dict.fromkeys(log_events or []))  # deduplicated, order-preserved

    prompt = (
        f"{_FAULT_KNOWLEDGE}\n"
        "---\n"
        "Given the incident below, identify which fault is active and return the single correct "
        "resolution endpoint path. Use the fault knowledge base above to match — pay close attention "
        "to log event names and message patterns.\n\n"
        f"Incident title: {title}\n"
        f"Services: {', '.join(services)}\n"
        f"Log events seen: {events_text or 'unknown'}\n"
        f"Sample log messages:\n{logs_text}\n\n"
        "Valid resolution endpoints (reply with ONLY the path, nothing else):\n"
        + "\n".join(f"  {ep}" for ep in _RESOLUTION_ENDPOINTS)
    )
    response = _bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    chosen = response["output"]["message"]["content"][0]["text"].strip()
    if chosen not in _RESOLUTION_ENDPOINTS:
        chosen = "/admin/rollback"
    return chosen


def summarize_incident(title: str, services: list, occurrences: int, log_message: str) -> str:
    prompt = (
        f"Summarize this software incident in 2-3 sentences for an on-call engineer.\n"
        f"Incident: {title}\n"
        f"Services affected: {', '.join(services)}\n"
        f"Sample error: {log_message}\n"
        f"Be concise. Focus on what failed and the likely impact."
    )
    response = _bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    return response["output"]["message"]["content"][0]["text"].strip()
