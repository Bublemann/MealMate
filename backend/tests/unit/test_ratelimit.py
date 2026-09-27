from dataclasses import dataclass

import pytest

from app.core import ratelimit
from app.core.ratelimit import LoginThrottle, RateLimits, RequestRateLimit


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
