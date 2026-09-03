import pytest
from fastapi import HTTPException

from app.core.rate_limit import (
    InMemoryRateLimitBackend,
    LoginRateLimiter,
    RedisRateLimitBackend,
)


def limiter(*, window_seconds: int = 60, **kwargs) -> LoginRateLimiter:
    return LoginRateLimiter(
        window_seconds=window_seconds,
        backend=InMemoryRateLimitBackend(window_seconds=window_seconds),
        **kwargs,
    )


async def test_check_passes_below_the_limit() -> None:
    rate_limiter = limiter(max_attempts=3)

    for _ in range(2):
        await rate_limiter.record_failure(["email:owner@example.com"])
    await rate_limiter.check(["email:owner@example.com"])  # must not raise


async def test_check_blocks_at_the_limit_with_retry_after() -> None:
    rate_limiter = limiter(max_attempts=3, window_seconds=45)

    for _ in range(3):
        await rate_limiter.record_failure(["email:owner@example.com"])

    with pytest.raises(HTTPException) as exc_info:
        await rate_limiter.check(["email:owner@example.com"])

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "45"


async def test_reset_clears_the_counter() -> None:
    rate_limiter = limiter(max_attempts=1)
    await rate_limiter.record_failure(["email:owner@example.com"])
    await rate_limiter.reset(["email:owner@example.com"])

    await rate_limiter.check(["email:owner@example.com"])  # must not raise


async def test_the_ip_bucket_is_looser_than_the_account_bucket() -> None:
    rate_limiter = limiter(max_attempts=2)
    rate_limiter.ip_limit_multiplier = 3

    for _ in range(5):
        await rate_limiter.record_failure(["ip:198.51.100.7"])
    await rate_limiter.check(["ip:198.51.100.7"])  # 5 < 2*3

    await rate_limiter.record_failure(["ip:198.51.100.7"])
    with pytest.raises(HTTPException):
        await rate_limiter.check(["ip:198.51.100.7"])


async def test_one_account_hit_from_many_ips_still_trips_the_email_bucket() -> None:
    rate_limiter = limiter(max_attempts=3)

    for octet in range(3):
        await rate_limiter.record_failure(
            [f"ip:198.51.100.{octet}", "email:owner@example.com"]
        )

    with pytest.raises(HTTPException):
        await rate_limiter.check(["ip:198.51.100.99", "email:owner@example.com"])


async def test_expired_attempts_fall_out_of_the_window() -> None:
    backend = InMemoryRateLimitBackend(window_seconds=0)
    rate_limiter = LoginRateLimiter(max_attempts=1, backend=backend)

    await rate_limiter.record_failure(["email:owner@example.com"])
    await rate_limiter.check(["email:owner@example.com"])  # window already elapsed


async def test_in_memory_backend_is_bounded() -> None:
    backend = InMemoryRateLimitBackend(window_seconds=60, max_keys=10)

    for index in range(50):
        await backend.record(f"email:user{index}@example.com")

    assert len(backend._attempts) <= 10
    # The oldest keys are evicted first, the newest are retained.
    assert await backend.count("email:user49@example.com") == 1
    assert await backend.count("email:user0@example.com") == 0


class FakeRedis:
    """Minimal stand-in covering the get/incr/expire/delete surface we use."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expiries: dict[str, int] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    def pipeline(self) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.operations: list[tuple] = []

    def incr(self, key: str) -> None:
        self.operations.append(("incr", key))

    def expire(self, key: str, seconds: int) -> None:
        self.operations.append(("expire", key, seconds))

    async def execute(self) -> None:
        for operation in self.operations:
            if operation[0] == "incr":
                self.redis.values[operation[1]] = self.redis.values.get(operation[1], 0) + 1
            else:
                self.redis.expiries[operation[1]] = operation[2]
        self.operations.clear()


async def test_redis_backend_counts_and_sets_a_ttl() -> None:
    redis = FakeRedis()
    backend = RedisRateLimitBackend(redis, window_seconds=60)

    await backend.record("email:owner@example.com")
    await backend.record("email:owner@example.com")

    assert await backend.count("email:owner@example.com") == 2
    assert redis.expiries["deploydock:login:email:owner@example.com"] == 60

    await backend.reset("email:owner@example.com")
    assert await backend.count("email:owner@example.com") == 0
