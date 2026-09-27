"""Weak ETags over response bodies, for polling with `If-None-Match` (plan § 5.8).

The tag is a SHA-256 over the serialized body as sent, so it is specific to the viewer and
changes with anything the response shows, not only with the list's version.
"""

import hashlib


def weak_etag(body: bytes) -> str:
    return f'W/"{hashlib.sha256(body).hexdigest()}"'


def _opaque(tag: str) -> str:
    return tag.strip().removeprefix("W/")


def matches(if_none_match: str | None, etag: str) -> bool:
    """Whether an `If-None-Match` header names the tag, by weak comparison (RFC 9110 § 13.1.2):
    `*`, or any of a comma-separated list with or without the `W/` prefix."""
    if if_none_match is None:
        return False
    if if_none_match.strip() == "*":
        return True
    return _opaque(etag) in {_opaque(tag) for tag in if_none_match.split(",")}
