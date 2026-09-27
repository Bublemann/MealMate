"""Settings, read from `MEALMATE_*` environment variables (plan § 5.12)."""

import re
from functools import cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_URL = "https://github.com/Bublemann/MealMate"
DATABASE_FILENAME = "mealmate.db"
MEDIA_DIRNAME = "media"
# `<data dir>/status/`: files the app and the host hand over (the backup request, plan § 11.1).
DATA_STATUS_DIRNAME = "status"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Open Food Facts' limit for product reads (BAR-08), for the app and the nightly job together.
OFF_REQUESTS_PER_MINUTE = 10

_COMMIT_SHA = re.compile(r"[0-9a-f]{7,40}")

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class BuildInfo(BaseSettings):
    """Version and commit baked into the image (`MEALMATE_VERSION`, `MEALMATE_COMMIT`)."""

    model_config = SettingsConfigDict(
        env_prefix="MEALMATE_", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    version: str = "0.0.0-dev"
    commit: str = "unknown"


class Settings(BuildInfo):
    """Runtime configuration. There is deliberately no default for the secret key (SEC-02)."""

    secret_key: SecretStr = Field(min_length=32)
    public_url: str | None = None
    data_dir: Path = Path("/data")
    # The host's status files (`backup.json`, `disk.json`), mounted read-only (plan § 11.1).
    status_dir: Path = Path("/status")
    # The digest of the running image, if the host passes it in (shown on the admin page). The
    # host passes its pin, `<repository>@sha256:…`; only the digest is kept.
    image_digest: str | None = None
    static_dir: Path | None = None
    cookie_secure: bool = True
    api_docs_enabled: bool = False
    diagnostics_enabled: bool = False
    log_level: LogLevel = "INFO"
    off_base_url: str = "https://world.openfoodfacts.org"
    off_refresh_days: int = Field(default=30, ge=1)
    off_user_agent_contact: str = REPO_URL
    # Open Food Facts requests started in any 60 s window by the app (lookups, background
    # refreshes) and by `mealmate jobs off-refresh`; together at most OFF_REQUESTS_PER_MINUTE,
    # as both may run at the same time (BAR-08).
    off_rate_app_per_minute: int = Field(default=6, ge=1)
    off_rate_job_per_minute: int = Field(default=4, ge=1)
    invite_ttl_days: int = Field(default=7, ge=1)
    reset_ttl_hours: int = Field(default=24, ge=1)
    session_idle_days: int = Field(default=90, ge=1)
    # bcrypt cost factor (plan § 5.4, O-7); tests use the minimum of 4.
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)

    @field_validator("public_url")
    @classmethod
    def _check_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("must be an absolute http(s) URL")
        return value.rstrip("/")

    @field_validator("image_digest")
    @classmethod
    def _digest_of_image_ref(cls, value: str | None) -> str | None:
        # `ghcr.io/…/mealmate@sha256:…` (the IMAGE_REF pin) or a bare `sha256:…`; empty = unknown.
        return (value or "").strip().rpartition("@")[2].strip() or None

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check_cookie_secure(self) -> Self:
        # Only E2E tests over plain HTTP on the loopback interface may drop `Secure` (plan § 9).
        if not self.cookie_secure:
            host = urlsplit(self.public_url).hostname if self.public_url else None
            if host not in LOOPBACK_HOSTS:
                raise ValueError(
                    "cookie_secure may only be false when public_url is a loopback address"
                )
        return self

    @model_validator(mode="after")
    def _check_off_rates(self) -> Self:
        if self.off_rate_app_per_minute + self.off_rate_job_per_minute > OFF_REQUESTS_PER_MINUTE:
            raise ValueError(
                "off_rate_app_per_minute + off_rate_job_per_minute must be at most "
                f"{OFF_REQUESTS_PER_MINUTE} (Open Food Facts' limit)"
            )
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / DATABASE_FILENAME

    @property
    def media_dir(self) -> Path:
        """Meal photos (plan § 5.10), outside any web root."""
        return self.data_dir / MEDIA_DIRNAME

    @property
    def data_status_dir(self) -> Path:
        """Where the admin page leaves the backup request for the host (OPS-08)."""
        return self.data_dir / DATA_STATUS_DIRNAME


def source_url(commit: str) -> str:
    """The source of the running build: the exact commit if known, else the repository."""
    return f"{REPO_URL}/tree/{commit}" if _COMMIT_SHA.fullmatch(commit) else REPO_URL


@cache
def get_settings() -> Settings:
    """The process-wide settings; fails if `MEALMATE_SECRET_KEY` is missing or too short."""
    return Settings()
