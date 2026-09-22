"""In-memory sliding window rate limiter for upload endpoints.

Protects against automated flood and queue starvation attacks while
remaining completely unobtrusive to legitimate users (e.g. 30 uploads/minute/IP).
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from typing import NamedTuple

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger("rate_limiter")


class RateLimitResult(NamedTuple):
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter with auto-eviction."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int = 60,
    ) -> None:
        self.max_requests = max_requests or settings.rate_limit_per_minute
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._history: dict[str, collections.deque[float]] = {}
        self._last_cleanup = time.monotonic()

    def check(self, key: str) -> RateLimitResult:
        """Check and record a request for the given key."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # Periodic cleanup of idle keys every 5 minutes
            if now - self._last_cleanup > 300:
                self._prune_stale_keys(cutoff)
                self._last_cleanup = now

            queue = self._history.setdefault(key, collections.deque())

            # Evict timestamps older than sliding window
            while queue and queue[0] <= cutoff:
                queue.popleft()

            count = len(queue)
            limit = self.max_requests

            if count >= limit:
                earliest = queue[0]
                retry_after = max(1, int(self.window_seconds - (now - earliest)))
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    retry_after=retry_after,
                )

            queue.append(now)
            remaining = limit - len(queue)
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=remaining,
                retry_after=0,
            )

    def _prune_stale_keys(self, cutoff: float) -> None:
        """Remove empty or idle queues to prevent memory accumulation."""
        idle_keys = [
            k for k, q in self._history.items() if not q or q[-1] <= cutoff
        ]
        for k in idle_keys:
            del self._history[k]

    def reset(self) -> None:
        """Reset all rate limiter state (useful for testing)."""
        with self._lock:
            self._history.clear()


upload_rate_limiter = SlidingWindowRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract client IP, taking proxy headers into account safely."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First entry is client IP in X-Forwarded-For
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip
    client = request.client
    return client.host if client else "127.0.0.1"


def enforce_upload_rate_limit(request: Request) -> None:
    """Dependency / guard that enforces upload rate limits."""
    client_ip = get_client_ip(request)
    res = upload_rate_limiter.check(client_ip)
    if not res.allowed:
        logger.warning(
            "Rate limit exceeded for client_ip=%s (retry_after=%ds)",
            client_ip,
            res.retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Terlalu banyak permintaan upload dari perangkat Anda ({res.limit}/menit). "
                f"Harap tunggu {res.retry_after} detik sebelum mencoba kembali."
            ),
            headers={"Retry-After": str(res.retry_after)},
        )
