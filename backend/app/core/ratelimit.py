"""In-memory rate limits (ACC-11, SEC-05, plan § 5.4).

The app runs as a single process (`--workers 1`), so the state lives in memory and is lost on
restart, which is acceptable for a household instance. Both limiters take a monotonic clock that
tests replace.

- `LoginThrottle`: failed logins per key (the normalised username, and the client IP). From the
  fifth failure within 15 minutes on, further attempts wait `2 ** (failures - 5)` seconds (at most
  60) after the last failure. There is no lockout, and a successful login clears the key.
- `RequestRateLimit`: at most N requests per key in a sliding window (join, reset, code checks).
"""

import math
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

type Clock = Callable[[], float]

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_FREE_FAILURES = 5
LOGIN_MAX_DELAY_SECONDS = 60
CODE_REQUESTS_PER_MINUTE = 10
# Bounds on the memory an attacker can make us hold.
_MAX_EVENTS_PER_KEY = 64
_PRUNE_ABOVE_KEYS = 10_000


def _retry_after(seconds: float) -> int:
    """Whole seconds for `Retry-After`, never 0."""
    return max(1, math.ceil(seconds))


@dataclass
class LoginThrottle:
    clock: Clock = time.monotonic
    window: float = LOGIN_WINDOW_SECONDS
    free_failures: int = LOGIN_FREE_FAILURES
    max_delay: float = LOGIN_MAX_DELAY_SECONDS
    _failures: dict[str, deque[float]] = field(default_factory=dict, repr=False)

    def _recent(self, key: str, now: float) -> deque[float] | None:
        failures = self._failures.get(key)
        if failures is None:
            return None
        while failures and failures[0] <= now - self.window:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures

    def delay(self, key: str) -> float:
        """Seconds until `key` may try again; 0 if it may try now."""
        now = self.clock()
        failures = self._recent(key, now)
        if failures is None or len(failures) < self.free_failures:
            return 0.0
        wait = min(2.0 ** (len(failures) - self.free_failures), self.max_delay)
        return max(0.0, failures[-1] + wait - now)

    def retry_after(self, keys: Iterable[str]) -> int | None:
        """Whole seconds to wait if any of `keys` is throttled, else None."""
        delay = max((self.delay(key) for key in keys), default=0.0)
        return _retry_after(delay) if delay > 0 else None

    def record_failure(self, keys: Iterable[str]) -> None:
        now = self.clock()
        if len(self._failures) > _PRUNE_ABOVE_KEYS:
            for stale in list(self._failures):
                self._recent(stale, now)
        for key in keys:
            self._failures.setdefault(key, deque(maxlen=_MAX_EVENTS_PER_KEY)).append(now)

    def reset(self, keys: Iterable[str]) -> None:
        for key in keys:
            self._failures.pop(key, None)


@dataclass
class RequestRateLimit:
    limit: int
    window: float
    clock: Clock = time.monotonic
    _requests: dict[str, deque[float]] = field(default_factory=dict, repr=False)

    def hit(self, key: str) -> int | None:
        """Count a request for `key`; returns the seconds to wait if it is over the limit
        (that request is then not counted), else None."""
        now = self.clock()
        if len(self._requests) > _PRUNE_ABOVE_KEYS:
            for stale in [
                k for k, v in self._requests.items() if not v or v[-1] <= now - self.window
            ]:
                del self._requests[stale]
        requests = self._requests.setdefault(key, deque())
        while requests and requests[0] <= now - self.window:
            requests.popleft()
        if len(requests) >= self.limit:
            return _retry_after(requests[0] + self.window - now)
        requests.append(now)
        return None


@dataclass
class RateLimits:
    """All limiters of one app instance (`app.state.rate_limits`)."""

    clock: Clock = time.monotonic
    login: LoginThrottle = field(init=False)
    codes: RequestRateLimit = field(init=False)

    def __post_init__(self) -> None:
        self.login = LoginThrottle(clock=self.clock)
        self.codes = RequestRateLimit(limit=CODE_REQUESTS_PER_MINUTE, window=60, clock=self.clock)
