"""Who is making a request, as established by the access token and the database."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    """The authenticated user of a request. `role` comes from the database, never the token."""

    user_id: str
    session_id: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
