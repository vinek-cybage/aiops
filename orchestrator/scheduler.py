import time
from typing import Callable, Protocol


class Trigger(Protocol):
    def run(self, on_wake: Callable[[], None]) -> None: ...


class IntervalTrigger:
    """Wakes on_wake() on a fixed timer. Stage 1's only trigger implementation."""

    def __init__(self, interval_seconds: float):
        self.interval_seconds = interval_seconds

    def run(self, on_wake):
        while True:
            on_wake()
            time.sleep(self.interval_seconds)


class ListenNotifyTrigger:
    """Not implemented in Stage 1 — documented seam for a later push-based trigger.

    A future implementation would open a psycopg2 connection in autocommit mode,
    `LISTEN <channel>;`, block on select.select([conn], ...) for a NOTIFY, and call
    the same on_wake() closure used today. It requires no changes to poll_once —
    on_wake never knows or cares whether it was woken by a timer or a NOTIFY, and
    poll_once only depends on the since_checkpoint value threaded through by whoever
    calls on_wake. Also requires adding NOTIFY statements to the metrics/logs insert
    path (e.g. the telemetry-api or seed script), which is out of scope for Stage 1.
    """

    def __init__(self, channel: str):
        self.channel = channel

    def run(self, on_wake):
        raise NotImplementedError("ListenNotifyTrigger is a Stage 1 seam, not yet implemented")
