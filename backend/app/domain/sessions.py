"""The refresh-token state machine (plan § 5.4, SEC-03).

Every refresh presents one token of a session. What happens depends only on that token, its
session and the time, so the decision is a pure function; the service applies it.

- **Active** token (not superseded):
  - normal refresh: ROTATE, i.e. supersede it and its still-active siblings, issue a new token;
  - fork: FORK once (a new session); a forked token still rotates normally but forks no more.
- Token superseded **less than 60 s ago** (lost response, parallel refresh):
  - normal refresh: GRACE, i.e. issue a new token and revoke nothing;
  - fork: FORK_REFUSED, nothing revoked.
- Token superseded **60 s ago or longer**:
  - normal refresh: REUSE, i.e. revoke the whole session;
  - fork: FORK_REFUSED, nothing revoked.

Before that: a revoked session is REVOKED, and an idle-expired token or session is EXPIRED.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

REFRESH_GRACE = timedelta(seconds=60)


class RefreshOutcome(StrEnum):
    ROTATE = "rotate"
    GRACE = "grace"
    REUSE = "reuse"
    FORK = "fork"
    FORK_REFUSED = "fork_refused"
    EXPIRED = "expired"
    REVOKED = "revoked"


@dataclass(frozen=True)
class RefreshTokenState:
    """What the decision needs to know about the presented token and its session."""

    token_expires_at: datetime
    superseded_at: datetime | None
    forked_at: datetime | None
    session_expires_at: datetime
    session_revoked_at: datetime | None


def decide_refresh(state: RefreshTokenState, *, now: datetime, fork: bool) -> RefreshOutcome:
    if state.session_revoked_at is not None:
        return RefreshOutcome.REVOKED
    if state.token_expires_at <= now or state.session_expires_at <= now:
        return RefreshOutcome.EXPIRED
    if fork:
        if state.superseded_at is None and state.forked_at is None:
            return RefreshOutcome.FORK
        return RefreshOutcome.FORK_REFUSED
    if state.superseded_at is None:
        return RefreshOutcome.ROTATE
    if now - state.superseded_at < REFRESH_GRACE:
        return RefreshOutcome.GRACE
    return RefreshOutcome.REUSE
