"""Who owns per-household data: a couple, or a user without one (D-42, D-48)."""

import pytest

from app.domain.owners import OwnerKey


@pytest.mark.parametrize(
    ("couple_id", "user_id"),
    [("couple-1", None), (None, "user-1")],
)
def test_an_owner_is_a_couple_or_a_user(couple_id: str | None, user_id: str | None) -> None:
    key = OwnerKey(couple_id=couple_id, user_id=user_id)
    assert (key.couple_id, key.user_id) == (couple_id, user_id)


@pytest.mark.parametrize(("couple_id", "user_id"), [(None, None), ("couple-1", "user-1")])
def test_an_owner_is_exactly_one_of_them(couple_id: str | None, user_id: str | None) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        OwnerKey(couple_id=couple_id, user_id=user_id)
