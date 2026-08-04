"""
Traffic generator — mirrors the C# TrafficGeneratorService BackgroundService.
Fires 2-4 random GET /orders/1 or POST /orders/1/checkout every 300-800ms.
"""
import asyncio
import random

import httpx

import config


async def traffic_loop(base_url: str):
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
        while True:
            batch_size = random.randint(2, 4)
            tasks = [
                _safe_get(client)  if random.randint(0, 1) == 0 else _safe_post(client)
                for _ in range(batch_size)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            delay = random.randint(
                config.TRAFFIC_MIN_DELAY_MS,
                config.TRAFFIC_MAX_DELAY_MS,
            ) / 1000.0
            await asyncio.sleep(delay)


async def _safe_get(client: httpx.AsyncClient):
    try:
        await client.get("/orders/1")
    except Exception:
        pass


async def _safe_post(client: httpx.AsyncClient):
    try:
        await client.post("/orders/1/checkout", json={"orderId": 1, "amount": 249.99})
    except Exception:
        pass
