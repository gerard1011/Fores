"""In-memory rate limiting.

Sized for the deployment that actually exists: one container, published
directly, no auth. Three distinct guards, because they stop different things:

  * per-IP request rate      — one bad actor hammering the endpoint
  * per-IP concurrent streams — SSE holds the connection open, so a request
                                rate limit alone does not stop someone opening
                                fifty simultaneous streams
  * global in-flight cap      — the only one that actually bounds the Anthropic
                                bill, since with no auth an attacker can rotate
                                IPs and defeat anything keyed on address

Counters live in process memory and reset on restart, which is acceptable
here. If this ever runs behind a proxy or as more than one replica, two things
must change together: swap this store for Redis, and start trusting a
forwarded-for header (see client_ip below).
"""

import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request

from . import config


class RateLimited(Exception):
    """Rejected before any work started. Carries what the client should be told."""

    def __init__(self, message: str, retry_after: int, kind: str):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        # "rate" | "concurrency" | "capacity" — the UI words these differently:
        # a capacity rejection is not the caller's fault and is worth retrying
        # sooner than a rate rejection.
        self.kind = kind


def client_ip(request: Request) -> str:
    """The client address, deliberately ignoring X-Forwarded-For.

    Nothing sits in front of this service, so a forwarded-for header can only
    have been set by the caller. Honouring it would let anyone reset their own
    bucket by inventing an address. When a real proxy is introduced, trust it
    here *and* move the counters to a shared store — doing either alone is
    worse than doing neither.
    """
    return request.client.host if request.client else "unknown"


class _SlidingWindow:
    """Per-key request timestamps, pruned on read.

    A sliding log rather than a fixed window: at these limits the deques hold
    at most a few hundred floats, and it avoids the burst-across-the-boundary
    hole that fixed windows have.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str, limit: int, window: float, now: float) -> float | None:
        hits = self._hits[key]
        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            # Room frees up when the oldest hit falls out of the window.
            return max(1.0, hits[0] + window - now)

        hits.append(now)
        return None

    def forget_idle(self, now: float, window: float) -> None:
        """Drop keys with no hits in the window so one-off IPs do not accumulate."""
        cutoff = now - window
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]


class Limiter:
    # A threading.Lock, not an anyio/asyncio one, and that is deliberate.
    # Releasing a slot happens in a finally block that may be running because
    # the task was cancelled (the client hung up). Awaiting an async lock there
    # gets cancelled again immediately, so the decrement never lands and the
    # slot leaks for the life of the process. A plain lock cannot be cancelled.
    # Every critical section below is a handful of integer operations with no
    # I/O, so holding it never blocks the event loop meaningfully.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows = _SlidingWindow()
        self._streams_per_ip: dict[str, int] = {}
        self._inflight = 0
        self._last_sweep = time.monotonic()
        # Counts rejections so you can tell whether the limits are biting real
        # users or just catching abuse. Surfaced at /api/health.
        self.rejections: dict[str, int] = defaultdict(int)

    # --- request rate -----------------------------------------------------

    async def check_rate(self, ip: str, *, per_minute: int, per_hour: int | None = None) -> None:
        now = time.monotonic()
        with self._lock:
            self._maybe_sweep(now)

            retry = self._windows.check_and_record(f"m:{ip}", per_minute, 60.0, now)
            if retry is None and per_hour is not None:
                retry = self._windows.check_and_record(f"h:{ip}", per_hour, 3600.0, now)

            if retry is not None:
                self.rejections["rate"] += 1
                raise RateLimited(
                    "Too many requests. Please wait a moment before asking again.",
                    retry_after=int(retry) + 1,
                    kind="rate",
                )

    # --- concurrency ------------------------------------------------------

    @asynccontextmanager
    async def chat_slot(self, ip: str) -> AsyncIterator[None]:
        """Hold a per-IP stream slot and a global in-flight slot for the request.

        Both are taken and released together under one lock, so there is never
        a window where a request holds one but not the other — a partial
        acquire would bleed global capacity on every rejection.

        The release sits in a finally with a non-cancellable lock, which is
        what makes it survive a client hanging up mid-stream. Both the
        cancellation and the exception paths are covered in
        tests/test_limits.py.
        """
        with self._lock:
            # .get rather than indexing: this dict is not a defaultdict, because
            # indexing one inserts the key, and a rejected request would then be
            # remembered forever — inflating active_ips and growing without bound.
            if self._streams_per_ip.get(ip, 0) >= config.CHAT_STREAMS_PER_IP:
                self.rejections["concurrency"] += 1
                raise RateLimited(
                    "You already have a question in progress. Wait for it to finish.",
                    retry_after=5,
                    kind="concurrency",
                )
            if self._inflight >= config.GLOBAL_INFLIGHT:
                self.rejections["capacity"] += 1
                raise RateLimited(
                    "The assistant is busy right now. Try again shortly.",
                    retry_after=10,
                    kind="capacity",
                )
            self._streams_per_ip[ip] = self._streams_per_ip.get(ip, 0) + 1
            self._inflight += 1

        try:
            yield
        finally:
            with self._lock:
                self._inflight -= 1
                remaining = self._streams_per_ip.get(ip, 1) - 1
                if remaining <= 0:
                    self._streams_per_ip.pop(ip, None)
                else:
                    self._streams_per_ip[ip] = remaining

    # --- housekeeping -----------------------------------------------------

    def _maybe_sweep(self, now: float) -> None:
        """Forget idle IPs occasionally. Caller must hold the lock."""
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        self._windows.forget_idle(now, 3600.0)

    def snapshot(self) -> dict:
        return {
            "inflight": self._inflight,
            "global_capacity": config.GLOBAL_INFLIGHT,
            "active_ips": len(self._streams_per_ip),
            "rejections": dict(self.rejections),
        }


limiter = Limiter()
