"""The couple picker and the choices of the user filters (CPL-01, CPL-04, VIS-02, MEAL-10,
UI-02)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.accounts import (
    Account,
    error,
    fields,
    insert_user,
    make_couple,
    make_user,
    set_privacy,
)


def ref(user: Account, *, deactivated: bool = False) -> dict[str, Any]:
    return {"id": user.id, "display_name": user.display_name, "deactivated": deactivated}


async def test_list_users_for_the_couple_picker(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna", display_name="Anna")
    zoe = await make_user(app, api, "zoe", display_name="Zoë")
    ben = await make_user(app, api, "ben", display_name="ben")
    await insert_user(app, "gone", active=False)

    response = await api.get("/api/users", headers=anna.headers)

    assert response.status_code == 200
    assert response.json() == [ref(ben), ref(zoe)]


@pytest.fixture
async def people(app: FastAPI, api: AsyncClient) -> dict[str, Account]:
    return {
        name: await make_user(app, api, name, display_name=name.capitalize())
        for name in ("anna", "ben", "carl", "dora")
    }


async def visible(api: AsyncClient, user: Account, scope: str) -> list[dict[str, Any]]:
    response = await api.get(f"/api/users/visible?for={scope}", headers=user.headers)
    assert response.status_code == 200
    result: list[dict[str, Any]] = response.json()
    return result


async def test_visible_users_default_to_everyone(
    people: dict[str, Account], api: AsyncClient
) -> None:
    carl = people["carl"]
    expected = [ref(carl)] + [ref(people[name]) for name in ("anna", "ben", "dora")]
    assert await visible(api, carl, "meals") == expected
    assert await visible(api, carl, "lists") == expected


async def test_private_users_disappear_from_the_chips_but_not_for_their_partner(
    people: dict[str, Account], api: AsyncClient
) -> None:
    anna, ben, carl, dora = people.values()
    await make_couple(api, anna, ben)
    await set_privacy(api, ben, meals_public=False)
    await set_privacy(api, dora, lists_public=False)
    await set_privacy(api, carl, meals_public=False, lists_public=False)

    # Carl sees himself even though he is private.
    assert await visible(api, carl, "meals") == [ref(carl), ref(anna), ref(dora)]
    assert await visible(api, carl, "lists") == [ref(carl), ref(anna), ref(ben)]
    # Anna always sees her partner Ben (CPL-04).
    assert await visible(api, anna, "meals") == [ref(anna), ref(ben), ref(dora)]
    assert await visible(api, anna, "lists") == [ref(anna), ref(ben)]
    # Ben's own view.
    assert await visible(api, ben, "meals") == [ref(ben), ref(anna), ref(dora)]

    # After the couple ends, the privacy switch applies to Anna as well.
    assert (await api.delete("/api/couple", headers=anna.headers)).status_code == 204
    assert await visible(api, anna, "meals") == [ref(anna), ref(dora)]


async def test_the_partner_comes_right_after_oneself(
    people: dict[str, Account], api: AsyncClient
) -> None:
    anna, ben, carl, dora = people.values()
    await make_couple(api, anna, dora)

    for scope in ("meals", "lists"):
        assert await visible(api, anna, scope) == [ref(anna), ref(dora), ref(ben), ref(carl)]
        assert await visible(api, dora, scope) == [ref(dora), ref(anna), ref(ben), ref(carl)]
        assert await visible(api, carl, scope) == [ref(carl), ref(anna), ref(ben), ref(dora)]


async def test_deactivated_users_stay_visible_and_flagged(
    app: FastAPI, people: dict[str, Account], api: AsyncClient
) -> None:
    anna, ben, *_ = people.values()
    admin = await make_user(app, api, "admin", display_name="Admin", role="admin")
    await api.patch(f"/api/admin/users/{ben.id}", json={"is_active": False}, headers=admin.headers)
    chips = await visible(api, anna, "meals")
    assert ref(ben, deactivated=True) in chips


async def test_visible_users_needs_a_valid_scope(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    for query in ("", "?for=ingredients"):
        response = await api.get(f"/api/users/visible{query}", headers=anna.headers)
        assert response.status_code == 422
        assert error(response) == "common.validation"
    assert fields(response) == {("query", "for"): "invalid"}
