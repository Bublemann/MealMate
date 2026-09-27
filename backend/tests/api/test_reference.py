"""Reference data: categories and their order, units, cuisines, tags (REF-01..04, ADM-01)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.reference import CATEGORY_KEYS, CUISINE_KEYS
from app.domain.text import normalize
from app.models import AdminEvent, Cuisine, Tag
from tests.accounts import Account, FakeClock, error, fields, make_user, scalars

CATALOG_ROUTES = [
    ("GET", "/api/categories"),
    ("GET", "/api/units"),
    ("GET", "/api/cuisines"),
    ("POST", "/api/cuisines"),
    ("GET", "/api/tags"),
    ("GET", "/api/ingredients"),
    ("GET", "/api/ingredients/similar?name=x"),
    ("POST", "/api/ingredients"),
    ("GET", "/api/ingredients/x"),
    ("PATCH", "/api/ingredients/x"),
    ("GET", "/api/ingredients/x/products"),
    ("POST", "/api/products"),
    ("GET", "/api/products/x"),
    ("PATCH", "/api/products/x"),
    ("PUT", "/api/admin/categories/order"),
    ("POST", "/api/admin/ingredients/x/merge"),
    ("DELETE", "/api/admin/ingredients/x"),
]


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


@pytest.mark.parametrize(("method", "path"), CATALOG_ROUTES)
async def test_catalog_routes_need_a_login(api: AsyncClient, method: str, path: str) -> None:
    response = await api.request(method, path, json={})
    assert response.status_code == 401
    assert error(response) == "common.unauthorized"


async def test_categories_in_the_seeded_order(api: AsyncClient, anna: Account) -> None:
    response = await api.get("/api/categories", headers=anna.headers)
    assert response.status_code == 200
    categories = response.json()
    assert [(item["key"], item["sort_order"]) for item in categories] == [
        (key, position) for position, key in enumerate(CATEGORY_KEYS)
    ]
    assert len({item["id"] for item in categories}) == len(CATEGORY_KEYS)


async def test_units(api: AsyncClient, anna: Account) -> None:
    response = await api.get("/api/units", headers=anna.headers)
    assert response.status_code == 200
    assert response.json() == [
        {"unit": "g", "kind": "mass"},
        {"unit": "kg", "kind": "mass"},
        {"unit": "ml", "kind": "volume"},
        {"unit": "l", "kind": "volume"},
        {"unit": "piece", "kind": "count"},
        {"unit": "tbsp", "kind": "volume"},
        {"unit": "tsp", "kind": "volume"},
    ]


# --- cuisines (REF-03) -------------------------------------------------------------------------


async def post_cuisine(api: AsyncClient, user: Account, name: str) -> Any:
    return await api.post("/api/cuisines", json={"name": name}, headers=user.headers)


async def test_seeded_cuisines(api: AsyncClient, anna: Account) -> None:
    response = await api.get("/api/cuisines", headers=anna.headers)
    assert response.status_code == 200
    assert [(item["key"], item["name"]) for item in response.json()] == [
        (key, None) for key in CUISINE_KEYS
    ]


async def test_add_cuisines(app: FastAPI, api: AsyncClient, anna: Account) -> None:
    created = await post_cuisine(api, anna, "  Vietnamesisch ")
    assert created.status_code == 201
    assert created.json() == {"id": created.json()["id"], "key": None, "name": "Vietnamesisch"}
    await post_cuisine(api, anna, "Äthiopisch")

    again = await post_cuisine(api, anna, "VIETNAMESISCH")
    assert again.status_code == 200
    assert again.json() == created.json()
    spelled = await post_cuisine(api, anna, "Aethiopisch")
    assert spelled.status_code == 200
    assert spelled.json()["name"] == "Äthiopisch"

    cuisines = (await api.get("/api/cuisines", headers=anna.headers)).json()
    assert [item["key"] or item["name"] for item in cuisines] == [
        *CUISINE_KEYS,
        "Äthiopisch",
        "Vietnamesisch",
    ]
    rows = await scalars(app, select(Cuisine).where(Cuisine.key.is_(None)))
    assert {row.created_by for row in rows} == {anna.id}


async def test_a_seeded_cuisine_matches_its_key(api: AsyncClient, anna: Account) -> None:
    response = await post_cuisine(api, anna, "Italian")
    assert response.status_code == 200
    assert response.json()["key"] == "italian"
    assert response.json()["name"] is None


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("", "too_short"),
        ("   ", "too_short"),
        ("x" * 41, "too_long"),
        ("Thai‮", "invalid_format"),
        ("́", "invalid_format"),
    ],
)
async def test_invalid_cuisine_names(api: AsyncClient, anna: Account, name: str, code: str) -> None:
    response = await post_cuisine(api, anna, name)
    assert response.status_code == 422
    assert fields(response) == {("body", "name"): code}


async def test_cuisines_seeded_under_an_unknown_key_come_after_the_others(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    database = app.state.database
    async with database.write_sessions() as session, session.begin():
        session.add(Cuisine(key="nordic", name=None, name_norm="nordic"))
    await post_cuisine(api, anna, "Baskisch")
    cuisines = (await api.get("/api/cuisines", headers=anna.headers)).json()
    assert [item["key"] or item["name"] for item in cuisines][-2:] == ["nordic", "Baskisch"]


# --- tags (REF-04) -----------------------------------------------------------------------------


async def test_tags(app: FastAPI, api: AsyncClient, anna: Account) -> None:
    assert (await api.get("/api/tags", headers=anna.headers)).json() == []
    database = app.state.database
    names = ["Grillen", "Schnell", "Vegetarisch", "Süß", "Frühstück", "Grillabend"]
    async with database.write_sessions() as session, session.begin():
        session.add_all(Tag(name=name, name_norm=normalize(name)) for name in names)

    async def tag_names(query: str | None = None) -> list[str]:
        params = {} if query is None else {"q": query}
        response = await api.get("/api/tags", params=params, headers=anna.headers)
        assert response.status_code == 200
        return [item["name"] for item in response.json()]

    assert await tag_names() == sorted(names, key=normalize)
    assert await tag_names("GRILL") == ["Grillabend", "Grillen"]
    assert await tag_names("ll") == ["Grillabend", "Grillen", "Schnell"]
    assert await tag_names("sü") == ["Süß"]
    assert await tag_names("fruh") == ["Frühstück"]
    assert await tag_names("  ") == await tag_names()
    assert await tag_names("xyz") == []


async def test_at_most_20_tags(app: FastAPI, api: AsyncClient, anna: Account) -> None:
    database = app.state.database
    async with database.write_sessions() as session, session.begin():
        session.add_all(Tag(name=f"tag{i:02}", name_norm=f"tag{i:02}") for i in range(25))
    response = await api.get("/api/tags", params={"q": "tag"}, headers=anna.headers)
    assert [item["name"] for item in response.json()] == [f"tag{i:02}" for i in range(20)]


# --- category order (ADM-01) -------------------------------------------------------------------


async def put_order(api: AsyncClient, user: Account, ids: list[str]) -> Any:
    return await api.put(
        "/api/admin/categories/order", json={"category_ids": ids}, headers=user.headers
    )


async def test_reorder_categories(
    app: FastAPI, api: AsyncClient, admin: Account, clock: FakeClock
) -> None:
    ids = [item["id"] for item in (await api.get("/api/categories", headers=admin.headers)).json()]
    new_order = [ids[3], ids[0], *ids[1:3], *ids[4:]]

    response = await put_order(api, admin, new_order)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == new_order
    assert [item["sort_order"] for item in response.json()] == list(range(len(ids)))
    listed = (await api.get("/api/categories", headers=admin.headers)).json()
    assert listed == response.json()
    assert listed[0]["key"] == "cheese"
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert [(event["action"], event["details"], event["target"]) for event in events] == [
        ("category.reorder", {}, None)
    ]
    assert events[0]["actor"]["id"] == admin.id


@pytest.mark.parametrize(
    "change",
    [
        lambda ids: ids[1:],
        lambda ids: [*ids, ids[0]],
        lambda ids: [ids[0], *ids[:-1]],
        lambda ids: [*ids[:-1], "unknown"],
        lambda ids: [],
    ],
)
async def test_the_order_must_be_a_permutation(
    app: FastAPI, api: AsyncClient, admin: Account, change: Any
) -> None:
    ids = [item["id"] for item in (await api.get("/api/categories", headers=admin.headers)).json()]
    response = await put_order(api, admin, change(ids))
    assert response.status_code == 422
    assert fields(response) == {("body", "category_ids"): "invalid"}
    assert await scalars(app, select(AdminEvent.id)) == []


async def test_only_admins_reorder(api: AsyncClient, anna: Account) -> None:
    ids = [item["id"] for item in (await api.get("/api/categories", headers=anna.headers)).json()]
    response = await put_order(api, anna, ids[::-1])
    assert response.status_code == 403
    assert error(response) == "common.forbidden"
    listed = (await api.get("/api/categories", headers=anna.headers)).json()
    assert [item["id"] for item in listed] == ids
