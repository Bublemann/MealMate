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
