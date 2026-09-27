import random
import time
from dataclasses import dataclass, field

import pytest

from app.core import ratelimit
from app.core.ratelimit import LoginThrottle, RateLimits, RequestRateLimit, SlidingWindow


@dataclass
class Clock:
    now: float = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_five_failures_are_free(clock: Clock) -> None:
    throttle = LoginThrottle(clock=clock)
    for _ in range(4):
        throttle.record_failure(["user:anna"])
        assert throttle.delay("user:anna") == 0
    throttle.record_failure(["user:anna"])
    assert throttle.delay("user:anna") == 1
    assert throttle.retry_after(["user:anna", "ip:1.2.3.4"]) == 1
    assert throttle.retry_after(["ip:1.2.3.4"]) is None


def test_delay_doubles_and_is_capped(clock: Clock) -> None:
    throttle = LoginThrottle(clock=clock)
    delays = []
    for _ in range(12):
        throttle.record_failure(["k"])
        delays.append(throttle.delay("k"))
    assert delays == [0, 0, 0, 0, 1, 2, 4, 8, 16, 32, 60, 60]


def test_delay_counts_from_the_last_failure(clock: Clock) -> None:
    throttle = LoginThrottle(clock=clock)
    for _ in range(7):
        throttle.record_failure(["k"])
    assert throttle.delay("k") == 4
    clock.now += 2.5
    assert throttle.delay("k") == 1.5
    assert throttle.retry_after(["k"]) == 2  # whole seconds, rounded up
    clock.now += 1.5
    assert throttle.delay("k") == 0
    assert throttle.retry_after(["k"]) is None


def test_failures_leave_the_window(clock: Clock) -> None:
    throttle = LoginThrottle(clock=clock)
    for _ in range(5):
        throttle.record_failure(["k"])
    clock.now += 15 * 60
    assert throttle.delay("k") == 0
    assert "k" not in throttle._failures  # forgotten entirely
    throttle.record_failure(["k"])
    assert throttle.delay("k") == 0


def test_success_resets(clock: Clock) -> None:
    throttle = LoginThrottle(clock=clock)
    for _ in range(6):
        throttle.record_failure(["user:anna", "ip:x"])
    throttle.reset(["user:anna", "ip:x", "never-seen"])
    assert throttle.retry_after(["user:anna", "ip:x"]) is None


def test_stale_keys_are_pruned(clock: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "_PRUNE_ABOVE_KEYS", 3)
    throttle = LoginThrottle(clock=clock)
    for key in "abcd":
        throttle.record_failure([key])
    clock.now += 16 * 60
    throttle.record_failure(["e"])
    assert set(throttle._failures) == {"e"}


def test_request_rate_limit(clock: Clock) -> None:
    limit = RequestRateLimit(limit=3, window=60, clock=clock)
    assert [limit.hit("ip") for _ in range(3)] == [None, None, None]
    assert limit.hit("ip") == 60
    assert limit.hit("other") is None
    clock.now += 59.5
    assert limit.hit("ip") == 1
    clock.now += 0.5
    assert limit.hit("ip") is None  # the first request left the window


def test_request_rate_limit_prunes_idle_keys(clock: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "_PRUNE_ABOVE_KEYS", 2)
    limit = RequestRateLimit(limit=3, window=60, clock=clock)
    for key in "abc":
        limit.hit(key)
    clock.now += 61
    limit.hit("d")
    assert set(limit._requests) == {"d"}


def test_rate_limits_share_the_clock(clock: Clock) -> None:
    limits = RateLimits(clock=clock)
    assert limits.login.clock is clock
    assert limits.codes.clock is clock
    assert limits.codes.limit == 10


def test_refund_takes_back_one_failure(clock: Clock) -> None:
    throttle = LoginThrottle(clock=clock)
    first = throttle.record_failure(["ip:x"])
    clock.now += 1
    second = throttle.record_failure(["ip:x", "user:anna"])
    clock.now += 1
    throttle.record_failure(["ip:x"])

    throttle.refund(["ip:x", "user:anna", "never-seen"], second)

    assert list(throttle._failures["ip:x"]) == [first, first + 2]
    assert "user:anna" not in throttle._failures
    throttle.refund(["ip:x"], second)  # already taken back: nothing happens
    assert len(throttle._failures["ip:x"]) == 2


# --- the Open Food Facts sliding window (BAR-08) ------------------------------------------------


@dataclass
class FakeSleep:
    """Sleeping moves the clock instead of waiting."""

    clock: Clock
    slept: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.clock.now += seconds


def max_in_any_window(starts: list[float], window: float = 60) -> int:
    """The most starts in any half-open `window` (it suffices to try each start as its
    beginning)."""
    return max(sum(first <= other < first + window for other in starts) for first in starts)


def test_window_allows_n_then_waits_for_the_oldest(clock: Clock) -> None:
    limit = SlidingWindow(6, clock=clock)
    assert [limit.reserve(max_wait=0) for _ in range(6)] == [0.0] * 6
    assert limit.reserve(max_wait=0) is None  # nothing reserved
    clock.now += 10
    assert limit.reserve(max_wait=50) == 50  # 60 s after the first start
    assert limit.reserve(max_wait=49) is None
    assert limit.reserve(max_wait=None) == 50  # also 60 s after the second one
    clock.now += 50  # the first six leave the window as the seventh and eighth start
    assert [limit.reserve(max_wait=0) for _ in range(4)] == [0.0] * 4
    assert limit.reserve(max_wait=0) is None
    clock.now += 60
    assert [limit.reserve(max_wait=0) for _ in range(6)] == [0.0] * 6


def test_never_more_than_n_starts_in_any_window(clock: Clock) -> None:
    """Callers arriving at random, some waiting as long as needed, some at most 5 s."""
    rng = random.Random(7)  # noqa: S311 -- reproducible test data
    limit = SlidingWindow(4, clock=clock)
    starts: list[float] = []
    for _ in range(500):
        clock.now += rng.choice([0, 0, 0.5, 3, 11, 29])
        wait = limit.reserve(max_wait=rng.choice([None, 0, 5]))
        if wait is not None:
            starts.append(clock.now + wait)
    assert starts == sorted(starts)  # served in order
    assert max_in_any_window(starts) == 4
    assert max_in_any_window(starts, window=59.9) == 4
    assert len(starts) > 100


async def test_window_callers_wait_their_turn(clock: Clock) -> None:
    sleep = FakeSleep(clock)
    limit = SlidingWindow(6, clock=clock, sleep=sleep)
    for _ in range(6):
        assert await limit.acquire(max_wait=5)
        clock.now += 1
    assert not await limit.acquire(max_wait=5)  # 54 s away: `off.busy` for a lookup
    clock.now += 50
    assert await limit.acquire(max_wait=5)  # 4 s away: worth the wait
    assert sleep.slept == [4]
    assert await limit.acquire()  # the refresh job waits as long as needed
    assert sleep.slept == [4, 1]
    assert clock.now == 1_061


def test_window_uses_real_time_by_default() -> None:
    limit = SlidingWindow(6)
    assert (limit.clock, limit.window) == (time.monotonic, 60)
    assert limit.reserve(max_wait=0) == 0.0
