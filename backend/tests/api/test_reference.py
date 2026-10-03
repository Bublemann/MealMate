"""Reference data: categories and their order, units, cuisines, tags (REF-01..04, ADM-01)."""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.reference import CATEGORY_KEYS, CUISINE_KEYS, SEEDED_CATEGORIES
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
    ("GET", "/api/ingredients/lookup?barcode=4006381333931"),
    ("GET", "/api/ingredients/off-search?q=milch"),
    ("POST", "/api/ingredients/x/barcode"),
    ("POST", "/api/ingredients/x/pending-update/apply"),
    ("POST", "/api/ingredients/x/pending-update/ignore"),
    ("PUT", "/api/admin/categories/order"),
    ("POST", "/api/admin/categories"),
    ("PATCH", "/api/admin/categories/x"),
    ("GET", "/api/admin/categories/x/usage"),
    ("DELETE", "/api/admin/categories/x"),
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


async def test_categories_have_a_name_per_language(api: AsyncClient, anna: Account) -> None:
    """I18N-04, D-31: each category comes with its names by UI language, next to its id, key,
    sort order and whether it is deleted (D-30). *Uncategorized* is seeded last (REF-01)."""
    response = await api.get("/api/categories", headers=anna.headers)
    categories = response.json()
    first, *_, other, last = categories
    assert first == {
        "id": first["id"],
        "key": "fruit_vegetables",
        "names": {"de": "Obst & Gemüse", "en": "Fruit & vegetables"},
        "sort_order": 0,
        "deleted": False,
    }
    assert (other["key"], other["names"]) == ("other", {"de": "Sonstiges", "en": "Other"})
    assert (last["key"], last["names"]) == (
        "uncategorized",
        {"de": "Ohne Kategorie", "en": "Uncategorized"},
    )
    assert [(item["key"], item["names"]) for item in categories] == [
        (category.key, {"de": category.name_de, "en": category.name_en})
        for category in SEEDED_CATEGORIES
    ]


async def test_units(api: AsyncClient, anna: Account) -> None:
    """In display order, each with the base units it fits (REF-02)."""
    response = await api.get("/api/units", headers=anna.headers)
    assert response.status_code == 200
    assert response.json() == [
        {"unit": "g", "kind": "mass", "base_units": ["g"]},
        {"unit": "kg", "kind": "mass", "base_units": ["g"]},
        {"unit": "ml", "kind": "volume", "base_units": ["ml"]},
        {"unit": "l", "kind": "volume", "base_units": ["ml"]},
        {"unit": "piece", "kind": "count", "base_units": ["piece"]},
        {"unit": "tbsp", "kind": "volume", "base_units": ["g", "ml"]},
        {"unit": "tsp", "kind": "volume", "base_units": ["g", "ml"]},
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


# --- adding and renaming categories (REF-01, ADM-01) -------------------------------------------


async def post_category(api: AsyncClient, user: Account, de: str, en: str) -> Any:
    return await api.post(
        "/api/admin/categories", json={"names": {"de": de, "en": en}}, headers=user.headers
    )


async def patch_category(
    api: AsyncClient, user: Account, category_id: str, de: str, en: str
) -> Any:
    return await api.patch(
        f"/api/admin/categories/{category_id}",
        json={"names": {"de": de, "en": en}},
        headers=user.headers,
    )


async def listed_categories(api: AsyncClient, user: Account) -> list[Any]:
    response = await api.get("/api/categories", headers=user.headers)
    assert response.status_code == 200
    categories: list[Any] = response.json()
    return categories


async def category_events(api: AsyncClient, admin: Account) -> list[tuple[str, Any]]:
    """The category events of the activity log, oldest first."""
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    return [
        (event["action"], event["details"])
        for event in reversed(events)
        if event["action"].startswith("category.")
    ]


async def test_add_categories_at_the_end_of_the_order(
    api: AsyncClient, admin: Account, anna: Account
) -> None:
    """REF-01: a new category has both names, no key, and goes last in the walking order."""
    response = await post_category(api, admin, "  Käsetheke ", " Cheese counter  ")

    assert response.status_code == 201
    counter = response.json()
    assert counter == {
        "id": counter["id"],
        "key": None,
        "names": {"de": "Käsetheke", "en": "Cheese counter"},
        "sort_order": len(CATEGORY_KEYS),
        "deleted": False,
    }
    bakery = (await post_category(api, admin, "Backstube", "Bakehouse")).json()
    assert bakery["sort_order"] == len(CATEGORY_KEYS) + 1
    listed = await listed_categories(api, anna)
    assert [item["key"] for item in listed] == [*CATEGORY_KEYS, None, None]
    assert listed[-2:] == [counter, bakery]
    assert [item["sort_order"] for item in listed] == list(range(len(listed)))
    assert await category_events(api, admin) == [
        ("category.create", {"name_de": "Käsetheke", "name_en": "Cheese counter"}),
        ("category.create", {"name_de": "Backstube", "name_en": "Bakehouse"}),
    ]


async def test_a_new_category_takes_part_in_the_order(api: AsyncClient, admin: Account) -> None:
    """ADM-01: the order is a permutation of every category, the new one included."""
    counter = (await post_category(api, admin, "Käsetheke", "Cheese counter")).json()
    ids = [item["id"] for item in await listed_categories(api, admin)]

    assert (await put_order(api, admin, ids[:-1])).status_code == 422
    response = await put_order(api, admin, [counter["id"], *ids[:-1]])

    assert response.status_code == 200
    listed = await listed_categories(api, admin)
    assert [item["id"] for item in listed] == [counter["id"], *ids[:-1]]
    assert listed[0]["sort_order"] == 0


async def test_rename_a_seeded_category(api: AsyncClient, admin: Account, anna: Account) -> None:
    """REF-01: seeded categories can be renamed too; both names are replaced, the key and the
    place in the walking order stay."""
    cheese = next(item for item in await listed_categories(api, anna) if item["key"] == "cheese")

    response = await patch_category(api, admin, cheese["id"], " Käsetheke ", "Cheese counter")

    assert response.status_code == 200
    renamed = {**cheese, "names": {"de": "Käsetheke", "en": "Cheese counter"}}
    assert response.json() == renamed
    assert renamed in await listed_categories(api, anna)
    assert await category_events(api, admin) == [
        (
            "category.rename",
            {
                "old_name_de": "Käse",
                "old_name_en": "Cheese",
                "name_de": "Käsetheke",
                "name_en": "Cheese counter",
            },
        )
    ]


async def test_rename_an_added_category(api: AsyncClient, admin: Account) -> None:
    counter = (await post_category(api, admin, "Käsetheke", "Cheese counter")).json()

    response = await patch_category(api, admin, counter["id"], "Käsetheke", "Cheese bar")

    assert response.status_code == 200
    assert response.json() == {**counter, "names": {"de": "Käsetheke", "en": "Cheese bar"}}
    assert (await listed_categories(api, admin))[-1] == response.json()


async def test_a_category_keeps_its_own_name(api: AsyncClient, admin: Account) -> None:
    """A category's own names never count as taken: it can change their spelling, and a rename
    that changes nothing logs nothing."""
    cheese = next(item for item in await listed_categories(api, admin) if item["key"] == "cheese")

    unchanged = await patch_category(api, admin, cheese["id"], "Käse", "Cheese")
    assert unchanged.status_code == 200
    assert await category_events(api, admin) == []

    respelled = await patch_category(api, admin, cheese["id"], "KÄSE", "cheese")
    assert respelled.status_code == 200
    assert respelled.json()["names"] == {"de": "KÄSE", "en": "cheese"}
    assert [action for action, _ in await category_events(api, admin)] == ["category.rename"]


@pytest.mark.parametrize(
    ("de", "en", "taken"),
    [
        # Seeded names, ignoring case, umlauts and accents.
        ("kaese", "Cheese counter", {"de"}),
        ("Käsetheke", "CHEESE", {"en"}),
        ("  SOSSEN, gewürze & öle ", "Sauces", {"de"}),
        ("Getränke", "Drinks", {"de", "en"}),
        # An added name, spelled differently.
        ("Créme-Ecke", "Cream nook", {"de"}),
        ("Sahne", "cream córner", {"en"}),
    ],
)
async def test_names_are_unique_per_language(
    app: FastAPI, api: AsyncClient, admin: Account, de: str, en: str, taken: set[str]
) -> None:
    """REF-01: a name another category has in the same language is a field error there."""
    await post_category(api, admin, "Crème-Ecke", "Cream corner")
    before = await listed_categories(api, admin)

    response = await post_category(api, admin, de, en)

    assert response.status_code == 422
    assert error(response) == "common.validation"
    assert fields(response) == {("body", "names", language): "taken" for language in taken}
    assert await listed_categories(api, admin) == before
    assert [action for action, _ in await category_events(api, admin)] == ["category.create"]


async def test_a_name_may_repeat_across_languages(api: AsyncClient, admin: Account) -> None:
    """Names are unique per language only: "Frozen" is a German name nobody uses yet."""
    response = await post_category(api, admin, "Frozen", "Feinkost")
    assert response.status_code == 201
    response = await post_category(api, admin, "Feinkost", "Fine food")
    assert response.status_code == 201


async def test_a_rename_to_a_taken_name(api: AsyncClient, admin: Account) -> None:
    categories = await listed_categories(api, admin)
    cheese = next(item for item in categories if item["key"] == "cheese")

    response = await patch_category(api, admin, cheese["id"], "Käse", "Other")

    assert response.status_code == 422
    assert fields(response) == {("body", "names", "en"): "taken"}
    assert await listed_categories(api, admin) == categories
    assert await category_events(api, admin) == []


@pytest.mark.parametrize(
    ("names", "problems"),
    [
        ({}, {("body", "names", "de"): "required", ("body", "names", "en"): "required"}),
        ({"de": "Käsetheke"}, {("body", "names", "en"): "required"}),
        ({"de": "", "en": "Cheese counter"}, {("body", "names", "de"): "too_short"}),
        ({"de": "Käsetheke", "en": "   "}, {("body", "names", "en"): "too_short"}),
        ({"de": "x" * 41, "en": "Cheese counter"}, {("body", "names", "de"): "too_long"}),
        ({"de": "Käsetheke", "en": "Cheese‮"}, {("body", "names", "en"): "invalid_format"}),
        ({"de": "́", "en": "Cheese counter"}, {("body", "names", "de"): "invalid_format"}),
    ],
)
async def test_invalid_category_names(
    app: FastAPI,
    api: AsyncClient,
    admin: Account,
    names: dict[str, str],
    problems: dict[tuple[str, ...], str],
) -> None:
    """Both names are required, trimmed and at most 40 characters."""
    cheese = next(item for item in await listed_categories(api, admin) if item["key"] == "cheese")
    for response in (
        await api.post("/api/admin/categories", json={"names": names}, headers=admin.headers),
        await api.patch(
            f"/api/admin/categories/{cheese['id']}", json={"names": names}, headers=admin.headers
        ),
    ):
        assert response.status_code == 422
        assert fields(response) == problems
    assert await scalars(app, select(AdminEvent.id)) == []


async def test_names_of_40_characters(api: AsyncClient, admin: Account) -> None:
    longest = "K" * 40
    response = await post_category(api, admin, f" {longest} ", "Cheese counter")
    assert response.status_code == 201
    assert response.json()["names"]["de"] == longest


async def test_rename_an_unknown_category(api: AsyncClient, admin: Account) -> None:
    response = await patch_category(api, admin, str(uuid.uuid7()), "Käsetheke", "Cheese counter")
    assert response.status_code == 404
    assert error(response) == "common.not_found"


async def test_only_admins_add_and_rename(app: FastAPI, api: AsyncClient, anna: Account) -> None:
    """REF-01, ADM-01: the categories are shared, so only admins change them."""
    categories = await listed_categories(api, anna)
    cheese = next(item for item in categories if item["key"] == "cheese")

    for response in (
        await post_category(api, anna, "Käsetheke", "Cheese counter"),
        await patch_category(api, anna, cheese["id"], "Käsetheke", "Cheese counter"),
    ):
        assert response.status_code == 403
        assert error(response) == "common.forbidden"
    assert await listed_categories(api, anna) == categories
    assert await scalars(app, select(AdminEvent.id)) == []
