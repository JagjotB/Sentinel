from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


class CircuitOpenError(RuntimeError):
    pass


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_after_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.reset_after_seconds:
            self.failures = 0
            self.opened_at = None
            return
        raise CircuitOpenError("circuit breaker is open")

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


async def with_retries[ResultT](
    operation: Callable[[], Awaitable[ResultT]],
    *,
    retries: int,
    timeout_seconds: float,
    retryable: Callable[[Exception], bool],
    breaker: CircuitBreaker | None = None,
    base_delay: float = 0.01,
) -> tuple[ResultT, int]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if breaker:
            breaker.before_call()
        try:
            result = await asyncio.wait_for(operation(), timeout=timeout_seconds)
            if breaker:
                breaker.success()
            return result, attempt
        except Exception as exc:
            last_error = exc
            can_retry = retryable(exc)
            if breaker and can_retry:
                breaker.failure()
            if attempt >= retries or not can_retry:
                raise
            await asyncio.sleep(base_delay * (2**attempt))
    assert last_error is not None
    raise last_error
