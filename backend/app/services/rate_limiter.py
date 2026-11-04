"""In-memory sliding window rate limiter for upload endpoints.

Protects against automated flood and queue starvation attacks. Bucket identity
is the caller's valid API key when present, otherwise the client IP.
"""

from __future__ import annotations

import collections
import hashlib
import logging
import threading
import time
from typing import NamedTuple

from fastapi import HTTPException, Request, Response

from app.config import settings
from app.services.api_key_auth import extract_key_from_request, validate_api_key

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
    """Extract client IP; X-Forwarded-For is only honoured behind a trusted proxy."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First entry is the client IP in X-Forwarded-For.
            ip = forwarded.split(",")[0].strip()
            if ip:
                return ip
    client = request.client
    return client.host if client else "127.0.0.1"


def get_client_identity(request: Request) -> str:
    """Bucket per pemanggil: API key valid bila ada, selain itu per IP.

    Portal kampus bisa berbagi satu IP (NAT/proxy) dan NIM tidak tersedia di
    request, jadi key pembatas yang stabil adalah API key pemanggil.
    """
    key = extract_key_from_request(request)
    if key and validate_api_key(key):
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return f"key:{digest}"
    return f"ip:{get_client_ip(request)}"


def enforce_upload_rate_limit(request: Request, response: Response | None = None) -> RateLimitResult:
    """Dependency / guard that enforces upload rate limits."""
    identity = get_client_identity(request)
    res = upload_rate_limiter.check(identity)
    if not res.allowed:
        logger.warning(
            "Rate limit exceeded for identity=%s (retry_after=%ds)",
            identity,
            res.retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Terlalu banyak permintaan upload dari pemanggil ini ({res.limit}/menit). "
                f"Harap tunggu {res.retry_after} detik sebelum mencoba kembali."
            ),
            headers={
                "Retry-After": str(res.retry_after),
                "X-RateLimit-Limit": str(res.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(res.retry_after),
            },
        )
    if response is not None:
        response.headers["X-RateLimit-Limit"] = str(res.limit)
        response.headers["X-RateLimit-Remaining"] = str(res.remaining)
        response.headers["X-RateLimit-Reset"] = "60"
    return res
