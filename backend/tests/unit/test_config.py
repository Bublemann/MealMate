from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import REPO_URL, BuildInfo, Settings, get_settings


def test_secret_key_is_required() -> None:
    with pytest.raises(ValidationError, match="secret_key"):
        Settings()
    with pytest.raises(ValidationError, match="secret_key"):
        get_settings()


def test_short_secret_key_is_rejected_without_echoing_it() -> None:
    too_short = "too-short-but-visible"
    with pytest.raises(ValidationError) as excinfo:
        Settings(secret_key=too_short)
    assert "at least 32" in str(excinfo.value)
    assert too_short not in str(excinfo.value)


def test_defaults(secret_key: str) -> None:
    settings = Settings(secret_key=secret_key)
    assert settings.secret_key.get_secret_value() == secret_key
    assert secret_key not in repr(settings)
    assert settings.public_url is None
    assert settings.data_dir == Path("/data")
    assert settings.database_path == Path("/data/mealmate.db")
    assert settings.static_dir is None
    assert settings.cookie_secure is True
    assert settings.api_docs_enabled is False
    assert settings.diagnostics_enabled is False
    assert settings.log_level == "INFO"
    assert settings.off_base_url == "https://world.openfoodfacts.org"
    assert settings.off_refresh_days == 30
    assert settings.off_user_agent_contact == REPO_URL
    assert (settings.off_rate_app_per_minute, settings.off_rate_job_per_minute) == (6, 4)
    assert (settings.invite_ttl_days, settings.reset_ttl_hours) == (7, 24)
    assert settings.session_idle_days == 90
    assert (settings.version, settings.commit) == ("0.0.0-dev", "unknown")


def test_reads_prefixed_environment(monkeypatch: pytest.MonkeyPatch, secret_key: str) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", secret_key)
    monkeypatch.setenv("MEALMATE_DATA_DIR", "/srv/data")
    monkeypatch.setenv("MEALMATE_STATIC_DIR", "/opt/mealmate/static")
    monkeypatch.setenv("MEALMATE_API_DOCS_ENABLED", "true")
    monkeypatch.setenv("MEALMATE_LOG_LEVEL", "debug")
    monkeypatch.setenv("MEALMATE_VERSION", "2.0.0-alpha.1")
    monkeypatch.setenv("MEALMATE_COMMIT", "0123abc")
    monkeypatch.setenv("SECRET_KEY", "unprefixed variables are ignored")

    settings = get_settings()

    assert settings.secret_key.get_secret_value() == secret_key
    assert settings.data_dir == Path("/srv/data")
    assert settings.static_dir == Path("/opt/mealmate/static")
    assert settings.api_docs_enabled is True
    assert settings.log_level == "DEBUG"
    assert (settings.version, settings.commit) == ("2.0.0-alpha.1", "0123abc")
    assert get_settings() is settings


def test_open_food_facts_rates_stay_within_its_limit(
    monkeypatch: pytest.MonkeyPatch, secret_key: str
) -> None:
    """The app and the nightly job may run at the same time: together at most 10 per minute
    (BAR-08)."""
    monkeypatch.setenv("MEALMATE_OFF_RATE_APP_PER_MINUTE", "7")
    monkeypatch.setenv("MEALMATE_OFF_RATE_JOB_PER_MINUTE", "3")
    settings = Settings(secret_key=secret_key)
    assert (settings.off_rate_app_per_minute, settings.off_rate_job_per_minute) == (7, 3)

    with pytest.raises(ValidationError, match="at most 10"):
        Settings(secret_key=secret_key, off_rate_app_per_minute=7, off_rate_job_per_minute=4)
    with pytest.raises(ValidationError, match="off_rate_job_per_minute"):
        Settings(secret_key=secret_key, off_rate_job_per_minute=0)


def test_build_info_needs_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEALMATE_VERSION", "2.0.0")
    assert BuildInfo().version == "2.0.0"


@pytest.mark.parametrize(
    "public_url", ["http://localhost:5173", "http://127.0.0.1:18080", "http://[::1]:8080"]
)
def test_insecure_cookies_allowed_on_loopback(secret_key: str, public_url: str) -> None:
    settings = Settings(secret_key=secret_key, public_url=public_url, cookie_secure=False)
    assert settings.cookie_secure is False


@pytest.mark.parametrize("public_url", [None, "https://mealmate.example.ts.net"])
def test_insecure_cookies_rejected_elsewhere(secret_key: str, public_url: str | None) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(secret_key=secret_key, public_url=public_url, cookie_secure=False)


def test_public_url_is_normalised(secret_key: str) -> None:
    settings = Settings(secret_key=secret_key, public_url="https://mealmate.example.ts.net/")
    assert settings.public_url == "https://mealmate.example.ts.net"


@pytest.mark.parametrize("public_url", ["mealmate.example.ts.net", "ftp://example.org", "https://"])
def test_public_url_must_be_http_url(secret_key: str, public_url: str) -> None:
    with pytest.raises(ValidationError, match="public_url"):
        Settings(secret_key=secret_key, public_url=public_url)


def test_invalid_log_level_is_rejected(secret_key: str) -> None:
    with pytest.raises(ValidationError, match="log_level"):
        Settings(secret_key=secret_key, log_level="verbose")
