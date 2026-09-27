"""What the account services need from the settings, derived once per app (or CLI run)."""

from dataclasses import dataclass
from datetime import timedelta

from app.core.config import Settings
from app.core.keys import DerivedKeys, derive_keys
from app.core.tokens import keyed_hash


@dataclass(frozen=True, repr=False)
class AuthConfig:
    keys: DerivedKeys
    public_url: str | None
    session_idle: timedelta
    invite_ttl: timedelta
    reset_ttl: timedelta
    bcrypt_rounds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> AuthConfig:
        return cls(
            keys=derive_keys(settings.secret_key),
            public_url=settings.public_url,
            session_idle=timedelta(days=settings.session_idle_days),
            invite_ttl=timedelta(days=settings.invite_ttl_days),
            reset_ttl=timedelta(hours=settings.reset_ttl_hours),
            bcrypt_rounds=settings.bcrypt_rounds,
        )

    def code_hash(self, code: str) -> str:
        """The HMAC stored for a refresh token, invite or reset code."""
        return keyed_hash(self.keys.token, code)
