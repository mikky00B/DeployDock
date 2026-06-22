from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status


class LoginRateLimiter:
    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 60) -> None:
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_seconds)
        self._attempts: dict[str, list[datetime]] = {}

    def check(self, key: str) -> None:
        now = datetime.now(UTC)
        attempts = self._recent_attempts(key, now)
        if len(attempts) >= self.max_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again shortly.",
            )
        self._attempts[key] = attempts

    def record_failure(self, key: str) -> None:
        now = datetime.now(UTC)
        self._attempts[key] = [*self._recent_attempts(key, now), now]

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)

    def _recent_attempts(self, key: str, now: datetime) -> list[datetime]:
        cutoff = now - self.window
        return [attempt for attempt in self._attempts.get(key, []) if attempt >= cutoff]


login_rate_limiter = LoginRateLimiter()
