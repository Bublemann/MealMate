from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.sessions import (
    REFRESH_GRACE,
    RefreshOutcome,
    RefreshTokenState,
    decide_refresh,
)

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=30)
ACTIVE = RefreshTokenState(
    token_expires_at=LATER,
    superseded_at=None,
    forked_at=None,
    session_expires_at=LATER,
    session_revoked_at=None,
)


def decide(state: RefreshTokenState, *, fork: bool = False) -> RefreshOutcome:
    return decide_refresh(state, now=NOW, fork=fork)


def superseded(ago: timedelta) -> RefreshTokenState:
    return replace(ACTIVE, superseded_at=NOW - ago)


def test_active_token_rotates() -> None:
    assert decide(ACTIVE) is RefreshOutcome.ROTATE


def test_forked_token_still_rotates() -> None:
    assert decide(replace(ACTIVE, forked_at=NOW - timedelta(days=1))) is RefreshOutcome.ROTATE


@pytest.mark.parametrize("ago", [timedelta(0), timedelta(seconds=1), timedelta(seconds=59.999)])
def test_recently_superseded_token_gets_grace(ago: timedelta) -> None:
    assert decide(superseded(ago)) is RefreshOutcome.GRACE


@pytest.mark.parametrize("ago", [REFRESH_GRACE, timedelta(seconds=61), timedelta(days=10)])
def test_old_superseded_token_is_reuse(ago: timedelta) -> None:
    assert decide(superseded(ago)) is RefreshOutcome.REUSE


def test_fork_needs_an_active_unforked_token() -> None:
    assert decide(ACTIVE, fork=True) is RefreshOutcome.FORK
    assert decide(replace(ACTIVE, forked_at=NOW), fork=True) is RefreshOutcome.FORK_REFUSED
    for ago in (timedelta(seconds=1), timedelta(days=1)):
        # Refused, never treated as reuse: nothing is revoked.
        assert decide(superseded(ago), fork=True) is RefreshOutcome.FORK_REFUSED


@pytest.mark.parametrize("fork", [False, True])
def test_revoked_session_wins(fork: bool) -> None:
    state = replace(superseded(timedelta(days=1)), session_revoked_at=NOW - timedelta(hours=1))
    assert decide(state, fork=fork) is RefreshOutcome.REVOKED
    assert decide(replace(ACTIVE, session_revoked_at=NOW), fork=fork) is RefreshOutcome.REVOKED


@pytest.mark.parametrize(
    "state",
    [
        replace(ACTIVE, token_expires_at=NOW),
        replace(ACTIVE, token_expires_at=NOW - timedelta(seconds=1)),
        replace(ACTIVE, session_expires_at=NOW),
        replace(superseded(timedelta(days=100)), session_expires_at=NOW - timedelta(days=1)),
    ],
)
@pytest.mark.parametrize("fork", [False, True])
def test_idle_expired(state: RefreshTokenState, fork: bool) -> None:
    assert decide(state, fork=fork) is RefreshOutcome.EXPIRED
