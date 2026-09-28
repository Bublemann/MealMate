"""System and diagnostics responses."""

from typing import Literal

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: Literal["ok"]


class VersionInfo(BaseModel):
    """What is running and where its source is (LIC-02, AGPL § 13)."""

    version: str
    commit: str
    source_url: str


class DiagCookieCheck(BaseModel):
    present: bool


class DiagRequestInfo(BaseModel):
    """The request as the app sees it (O-3); `None` where a header is missing."""

    client_host: str
    scheme: str
    host_header: str | None
    x_forwarded_for: str | None
    x_forwarded_proto: str | None
