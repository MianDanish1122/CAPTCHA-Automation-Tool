import time
import threading
from typing import Optional
from fastapi import Request, HTTPException, status
from app.config import settings
from app.services.client_ip import get_client_ip


class InMemoryRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Stores timestamps of requests per key and evicts expired records.
    Designed with a clean interface for Redis backend drop-in.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._requests: dict[str, list[float]] = {}

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60
    ) -> tuple[bool, int, int]:
        """
        Check whether a request is allowed under the sliding window.
        Returns:
            (allowed: bool, retry_after: int, remaining: int)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Clean expired timestamps
            timestamps = self._requests.get(key, [])
            valid_timestamps = [t for t in timestamps if t > window_start]

            if len(valid_timestamps) >= max_requests:
                earliest = valid_timestamps[0]
                retry_after = max(1, int(window_seconds - (now - earliest)))
                self._requests[key] = valid_timestamps
                return False, retry_after, 0

            # Record this request
            valid_timestamps.append(now)
            self._requests[key] = valid_timestamps
            remaining = max(0, max_requests - len(valid_timestamps))
            return True, 0, remaining

    def reset(self, key: Optional[str] = None):
        """Reset rate limiter state (useful in test suites)."""
        with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


limiter = InMemoryRateLimiter()


def rate_limit(max_requests: int, window_seconds: int = 60, scope: str = "general"):
    """
    FastAPI dependency for rate limiting endpoints.
    Enforces sliding-window rate limit based on client IP or authenticated user.
    """
    async def rate_limit_dependency(request: Request):
        # Forwarding headers are honored ONLY from configured trusted proxies.
        client_ip = get_client_ip(request)

        key = f"{scope}:{client_ip}"
        allowed, retry_after, remaining = limiter.check_rate_limit(
            key=key,
            max_requests=max_requests,
            window_seconds=window_seconds
        )

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {scope}. Please retry in {retry_after} seconds.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                }
            )

    return rate_limit_dependency
