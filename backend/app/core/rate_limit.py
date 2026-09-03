"""Login rate limiting.

Two backends:

* Redis (`REDIS_URL` set) - shared across uvicorn workers and API replicas, which
  is the only correct option for a multi-worker deployment.
* In-memory - a bounded LRU, used when no Redis URL is configured. It is
  per-process, so with more than one worker the effective limit is multiplied by
  the worker count. Acceptable for a single-process self-hosted install; the app
  logs a warning at startup when running with workers and no Redis.

Attempts are counted per client IP, per email, and per IP+email so that neither
a single account nor a single source can be hammered by spreading attempts.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

logger = logging.getLogger("deploydock.rate_limit")

MAX_TRACKED_KEYS = 10_000


class RateLimitBackend:
    async def count(self, key: str) -> int:  # pragma: no cover - interface
        raise NotImplementedError

    async def record(self, key: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def reset(self, key: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class InMemoryRateLimitBackend(RateLimitBackend):
    """Per-process sliding window with a hard cap on tracked keys."""

    def __init__(self, *, window_seconds: int, max_keys: int = MAX_TRACKED_KEYS) -> None:
        self.window = timedelta(seconds=window_seconds)
        self.max_keys = max_keys
        self._attempts: OrderedDict[str, list[datetime]] = OrderedDict()

    async def count(self, key: str) -> int:
        return len(self._recent(key))

    async def record(self, key: str) -> None:
        attempts = self._recent(key)
        attempts.append(datetime.now(UTC))
        self._attempts[key] = attempts
        self._attempts.move_to_end(key)
        while len(self._attempts) > self.max_keys:
            self._attempts.popitem(last=False)

    async def reset(self, key: str) -> None:
        self._attempts.pop(key, None)

    def _recent(self, key: str) -> list[datetime]:
        cutoff = datetime.now(UTC) - self.window
        attempts = [attempt for attempt in self._attempts.get(key, []) if attempt > cutoff]
        if attempts:
            self._attempts[key] = attempts
        else:
            self._attempts.pop(key, None)
        return attempts


class RedisRateLimitBackend(RateLimitBackend):
    """Shared counter with a TTL-based window."""

    def __init__(self, redis_client, *, window_seconds: int) -> None:
        self.redis = redis_client
        self.window_seconds = window_seconds

    async def count(self, key: str) -> int:
        value = await self.redis.get(self._key(key))
        return int(value) if value else 0

    async def record(self, key: str) -> None:
        redis_key = self._key(key)
        pipeline = self.redis.pipeline()
        pipeline.incr(redis_key)
        pipeline.expire(redis_key, self.window_seconds)
        await pipeline.execute()

    async def reset(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    @staticmethod
    def _key(key: str) -> str:
        return f"deploydock:login:{key}"


class LoginRateLimiter:
    def __init__(
        self,
        *,
        max_attempts: int = 5,
        window_seconds: int = 60,
        ip_limit_multiplier: int = 5,
        backend: RateLimitBackend | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.ip_limit_multiplier = ip_limit_multiplier
        self.window_seconds = window_seconds
        self.backend = backend or InMemoryRateLimitBackend(window_seconds=window_seconds)

    def limit_for(self, key: str) -> int:
        # A single IP can legitimately front many users (office NAT, reverse proxy),
        # so the per-IP bucket is deliberately looser than the per-account one.
        if key.startswith("ip:"):
            return self.max_attempts * self.ip_limit_multiplier
        return self.max_attempts

    async def check(self, keys: list[str]) -> None:
        for key in keys:
            if await self.backend.count(key) >= self.limit_for(key):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed login attempts. Try again shortly.",
                    headers={"Retry-After": str(self.window_seconds)},
                )

    async def record_failure(self, keys: list[str]) -> None:
        for key in keys:
            await self.backend.record(key)

    async def reset(self, keys: list[str]) -> None:
        for key in keys:
            await self.backend.reset(key)


login_rate_limiter = LoginRateLimiter()


def configure_login_rate_limiter(settings) -> LoginRateLimiter:
    """Point the shared limiter at Redis when configured. Called at startup."""
    global login_rate_limiter

    backend: RateLimitBackend
    if settings.redis_url:
        try:
            from redis.asyncio import from_url
        except ImportError:  # pragma: no cover - optional dependency
            logger.warning(
                "REDIS_URL is set but the redis package is not installed; "
                "falling back to the per-process rate limiter."
            )
            backend = InMemoryRateLimitBackend(window_seconds=settings.login_window_seconds)
        else:
            backend = RedisRateLimitBackend(
                from_url(settings.redis_url, decode_responses=True),
                window_seconds=settings.login_window_seconds,
            )
    else:
        logger.warning(
            "No REDIS_URL configured: login rate limiting is per-process. "
            "Run a single API worker, or set REDIS_URL, to make the limit accurate."
        )
        backend = InMemoryRateLimitBackend(window_seconds=settings.login_window_seconds)

    login_rate_limiter = LoginRateLimiter(
        max_attempts=settings.login_max_attempts,
        window_seconds=settings.login_window_seconds,
        backend=backend,
    )
    return login_rate_limiter
