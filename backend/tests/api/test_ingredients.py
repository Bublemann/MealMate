"""Ingredients: create (by hand and from Open Food Facts), barcode, search by name and brand, the
similar hint, edit, merge and delete (ING, NUT-02, BAR-01, BAR-03, BAR-04)."""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.models import AdminEvent, Ingredient
from app.services import hooks
from tests.accounts import Account, FakeClock, error, fields, make_user, scalars
from tests.catalog import (
    EAN_8,
    EAN_13,
    EAN_13_B,
    NO_NUTRIENTS,
    UPC_A,
    UPC_E,
    category_ids,
    create_from_off,
    create_ingredient,
    ref,
    set_stored,
)
from tests.lists import create_list, detail, extra_added, set_status, start_shopping
from tests.meals import create_meal


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


async def post(api: AsyncClient, user: Account, **body: Any) -> Any:
    return await api.post("/api/ingredients", json=body, headers=user.headers)


async def patch(api: AsyncClient, user: Account, ingredient_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/ingredients/{ingredient_id}", json=body, headers=user.headers)


async def get(api: AsyncClient, user: Account, ingredient_id: str) -> Any:
    response = await api.get(f"/api/ingredients/{ingredient_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def search(api: AsyncClient, user: Account, **params: str | list[str]) -> list[str]:
    """The labels found: the name, with the brand in brackets."""
    response = await api.get("/api/ingredients", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return [
        item["name"] if item["brand"] is None else f"{item['name']} ({item['brand']})"
        for item in response.json()
    ]


# --- create and read (ING-01, ING-02) ----------------------------------------------------------


async def test_create_with_defaults(api: AsyncClient, anna: Account) -> None:
    categories = await category_ids(api, anna)

    response = await post(api, anna, name="  Äpfel ")

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Äpfel",
        "brand": None,
        "barcode": None,
        "category_id": categories["other"],
        "base_unit": "g",
        "piece_weight_g": None,
        "nutrients": NO_NUTRIENTS,
        "quantity_text": None,
        "pack_quantity": None,
        "pack_unit": None,
        "source": "manual",
        "user_edited_fields": [],
        "off_last_modified_at": None,
        "fetched_at": None,
        "pending_update": None,
        "usage": {"meals": 0, "lists": 0},
        "created_by": ref(anna),
        "updated_by": ref(anna),
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:00:00Z",
    }
    assert await get(api, anna, body["id"]) == body


async def test_create_with_everything(api: AsyncClient, anna: Account) -> None:
    categories = await category_ids(api, anna)
    body = await create_ingredient(
        api,
        anna,
        "Milch",
        brand=" Weihenstephan ",
        barcode=" 4006381 333931 ",
        category_id=categories["dairy_eggs"],
        base_unit="ml",
        nutrients={"kcal": 64, "fat": 3.5, "sugar": None},
    )
    assert (body["name"], body["brand"], body["barcode"]) == ("Milch", "Weihenstephan", EAN_13)
    assert body["category_id"] == categories["dairy_eggs"]
    assert (body["base_unit"], body["piece_weight_g"]) == ("ml", None)
    assert body["nutrients"] == NO_NUTRIENTS | {"kcal": 64, "fat": 3.5}
    # Typed by hand: no pack size (D-38), nothing to refresh, nothing marked.
    assert (body["quantity_text"], body["pack_quantity"], body["pack_unit"]) == (None, None, None)
    assert (body["source"], body["user_edited_fields"], body["fetched_at"]) == ("manual", [], None)


async def test_empty_optional_texts_are_null(api: AsyncClient, anna: Account) -> None:
    body = await create_ingredient(api, anna, "Eier", brand="  ")
    assert body["brand"] is None
    body = await create_from_off(api, anna, "Milch", EAN_13, quantity_text=" ")
    assert body["quantity_text"] is None


async def test_names_need_not_be_unique(api: AsyncClient, anna: Account, ben: Account) -> None:
    """Two brands of the same thing are two ingredients; even the very same name and brand is
    only a hint, not an error."""
    first = await create_ingredient(api, anna, "Milch", brand="Weihenstephan")
    second = await create_ingredient(api, ben, "MILCH", brand="Landliebe")
    third = await create_ingredient(api, ben, "Milch", brand="Weihenstephan")
    assert len({first["id"], second["id"], third["id"]}) == 3
    assert await search(api, anna, q="milch") == [
        "MILCH (Landliebe)",
        "Milch (Weihenstephan)",
        "Milch (Weihenstephan)",
    ]


@pytest.mark.parametrize(
    ("body", "field", "code"),
    [
        ({"name": ""}, "name", "too_short"),
        ({"name": "   "}, "name", "too_short"),
        ({"name": "x" * 61}, "name", "too_long"),
        ({"name": "Äpfel‮"}, "name", "invalid_format"),
        ({"name": "Äp\nfel"}, "name", "invalid_format"),
        ({"name": "́"}, "name", "invalid_format"),
        ({"base_unit": "kg"}, "base_unit", "invalid"),
        ({"base_unit": "pieces"}, "base_unit", "invalid"),
        ({"base_unit": "piece", "piece_weight_g": 0}, "piece_weight_g", "out_of_range"),
        ({"base_unit": "piece", "piece_weight_g": 10_000.5}, "piece_weight_g", "out_of_range"),
        ({"piece_weight_g": 0}, "piece_weight_g", "out_of_range"),
        ({"piece_weight_g": 10_000.5}, "piece_weight_g", "out_of_range"),
        # Only an ingredient counted in pieces has a piece weight (D-32).
        ({"piece_weight_g": 60}, "piece_weight_g", "invalid"),
        ({"base_unit": "ml", "piece_weight_g": 1030}, "piece_weight_g", "invalid"),
        ({"barcode": ""}, "barcode", "too_short"),
        ({"barcode": "1" * 33}, "barcode", "too_long"),
        ({"brand": "x" * 81}, "brand", "too_long"),
        ({"brand": "\x07"}, "brand", "invalid_format"),
        ({"brand": "Hausmarke"}, "brand", "invalid_format"),
        ({"quantity_text": "x" * 41}, "quantity_text", "too_long"),
        ({"quantity_text": "500͸ g"}, "quantity_text", "invalid_format"),
        ({"pack_quantity": 0}, "pack_quantity", "out_of_range"),
        ({"pack_quantity": 100_001}, "pack_quantity", "out_of_range"),
        ({"pack_unit": "cup"}, "pack_unit", "invalid"),
        ({"category_id": "unknown"}, "category_id", "invalid"),
    ],
)
async def test_invalid_fields(
    api: AsyncClient, anna: Account, body: dict[str, Any], field: str, code: str
) -> None:
    response = await post(api, anna, **({"name": "Äpfel"} | body))
    assert response.status_code == 422
    assert fields(response) == {("body", field): code}


async def test_a_lone_surrogate_is_refused(api: AsyncClient, anna: Account) -> None:
    """JSON may escape half a UTF-16 pair (`\\ud800`), which cannot be stored as UTF-8;
    Pydantic refuses it as no valid string."""
    response = await api.post(
        "/api/ingredients",
        content=json.dumps({"name": "Pasta", "brand": "Barilla\ud800"}),
        headers=anna.headers | {"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert fields(response) == {("body", "brand"): "invalid"}


@pytest.mark.parametrize(
    ("nutrients", "field"),
    [
        ({"kcal": 900.5}, "kcal"),
        ({"kcal": -1}, "kcal"),
        ({"protein": 100.1}, "protein"),
        ({"carbs": 101}, "carbs"),
        ({"sugar": -0.1}, "sugar"),
        ({"fat": 1000}, "fat"),
    ],
)
async def test_implausible_nutrients(
    api: AsyncClient, anna: Account, nutrients: dict[str, float], field: str
) -> None:
    response = await post(api, anna, name="Äpfel", nutrients=nutrients)
    assert fields(response) == {("body", "nutrients", field): "out_of_range"}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize(
    ("body", "loc"),
    [
        ('{{"name": "Äpfel", "piece_weight_g": {value}}}', ("body", "piece_weight_g")),
        ('{{"name": "Äpfel", "nutrients": {{"kcal": {value}}}}}', ("body", "nutrients", "kcal")),
    ],
    ids=["piece_weight_g", "nutrients.kcal"],
)
async def test_numbers_must_be_finite(
    api: AsyncClient, anna: Account, value: str, body: str, loc: tuple[str, ...]
) -> None:
    """JSON bodies may spell NaN and Infinity; such numbers are out of range."""
    response = await api.post(
        "/api/ingredients",
        content=body.format(value=value).encode(),
        headers=anna.headers | {"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert fields(response) == {loc: "out_of_range"}


async def test_limits_are_inclusive(api: AsyncClient, anna: Account) -> None:
    body = await create_ingredient(
        api,
        anna,
        "Grenzfall",
        base_unit="piece",
        piece_weight_g=10_000,
        nutrients={"kcal": 900, "protein": 0, "carbs": 100, "sugar": 100, "fat": 100},
    )
    assert body["nutrients"] == {"kcal": 900, "protein": 0, "carbs": 100, "sugar": 100, "fat": 100}
    assert body["piece_weight_g"] == 10_000
    from_off = await create_from_off(api, anna, "Großpackung", EAN_13, pack_quantity=100_000)
    assert from_off["pack_quantity"] == 100_000


async def test_density_is_gone(app: FastAPI, api: AsyncClient, anna: Account) -> None:
    """D-32: no density in or out; one sent by an older app is ignored."""
    oil = await create_ingredient(api, anna, "Olivenöl", base_unit="ml", density_g_per_ml=0.92)
    assert "density_g_per_ml" not in oil
    body = (await patch(api, anna, oil["id"], density_g_per_ml=0.9)).json()
    assert "density_g_per_ml" not in body
    assert await scalars(app, select(Ingredient.density_g_per_ml)) == [None]


async def test_what_a_g_or_ml_ingredient_has_from_before_stays_hidden(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    """A piece weight and density from before D-32 are neither shown nor touched: they stay for
    the migration (D-34). A null piece weight is ignored; a new one is refused."""
    apples = await create_ingredient(api, anna, "Äpfel")
    await set_stored(app, apples["id"], piece_weight_g=180, density_g_per_ml=0.8)
    assert (await get(api, anna, apples["id"]))["piece_weight_g"] is None

    body = (await patch(api, anna, apples["id"], name="Apfel", piece_weight_g=None)).json()
    assert (body["name"], body["piece_weight_g"]) == ("Apfel", None)
    response = await patch(api, anna, apples["id"], name="Äpfel", piece_weight_g=150)
    assert fields(response) == {("body", "piece_weight_g"): "invalid"}
    assert await scalars(app, select(Ingredient.piece_weight_g)) == [180]
    assert await scalars(app, select(Ingredient.density_g_per_ml)) == [0.8]

    # Counted in millilitres, it still has it; counted in pieces, it has the piece weight sent
    # along, or none: the hidden one would surprise (ING-02).
    await patch(api, anna, apples["id"], base_unit="ml")
    await patch(api, anna, apples["id"], base_unit="g")
    assert await scalars(app, select(Ingredient.piece_weight_g)) == [180]
    body = (await patch(api, anna, apples["id"], base_unit="piece")).json()
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", None)
    await patch(api, anna, apples["id"], base_unit="g")
    await set_stored(app, apples["id"], piece_weight_g=180)
    body = (await patch(api, anna, apples["id"], base_unit="piece", piece_weight_g=150)).json()
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", 150)


async def test_unknown_ingredient(api: AsyncClient, anna: Account) -> None:
    for response in (
        await api.get("/api/ingredients/nope", headers=anna.headers),
        await patch(api, anna, "nope", name="x"),
        await api.post("/api/ingredients/nope/pending-update/apply", headers=anna.headers),
    ):
        assert response.status_code == 404
        assert error(response) == "common.not_found"


# --- barcodes (BAR-01) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("barcode", "stored"),
    [
        (EAN_13, EAN_13),
        (EAN_13_B, EAN_13_B),
        (UPC_A, f"0{UPC_A}"),
        (EAN_8, EAN_8),
        (UPC_E, "0042100005264"),
    ],
)
async def test_accepted_barcodes(
    api: AsyncClient, anna: Account, barcode: str, stored: str
) -> None:
    """Stored in one canonical form: GTIN-13, except EAN-8 (BAR-01)."""
    assert (await create_ingredient(api, anna, "Nudeln", barcode=barcode))["barcode"] == stored


@pytest.mark.parametrize(
    "barcode",
    ["4006381333932", "400638133393", "40063813339311", "abc", "4006-381333931", "\uff11\uff12"],
)
async def test_invalid_barcodes(api: AsyncClient, anna: Account, barcode: str) -> None:
    response = await post(api, anna, name="Nudeln", barcode=barcode)
    assert response.status_code == 422
    assert fields(response) == {("body", "barcode"): "invalid_format"}


@pytest.mark.parametrize(
    ("first", "second"),
    [(UPC_A, f"0{UPC_A}"), (f"0{UPC_A}", UPC_A), (UPC_E, "042100005264"), (UPC_E, "0042100005264")],
)
async def test_a_barcode_belongs_to_one_ingredient(
    app: FastAPI, api: AsyncClient, anna: Account, first: str, second: str
) -> None:
    """Also in another spelling of the same code (409 with the other ingredient's id)."""
    owner = await create_ingredient(api, anna, "Nudeln", barcode=first)
    response = await post(api, anna, name="Pasta", barcode=second)
    assert response.status_code == 409
    assert error(response) == "ingredient.barcode_taken"
    assert response.json()["params"] == {"ingredient_id": owner["id"]}
    assert await scalars(app, select(Ingredient.name)) == ["Nudeln"]


async def test_change_or_clear_the_barcode(api: AsyncClient, anna: Account) -> None:
    first = await create_ingredient(api, anna, "Nudeln", barcode=EAN_13)
    second = await create_ingredient(api, anna, "Reis")

    taken = await patch(api, anna, second["id"], barcode=EAN_13)
    assert taken.status_code == 409
    assert error(taken) == "ingredient.barcode_taken"
    invalid = await patch(api, anna, second["id"], barcode="123")
    assert fields(invalid) == {("body", "barcode"): "invalid_format"}
    # The edit form sets, replaces and clears a barcode on purpose.
    added = await patch(api, anna, second["id"], barcode=UPC_A)
    assert added.json()["barcode"] == f"0{UPC_A}"
    same = await patch(api, anna, first["id"], barcode=f" {EAN_13}")
    assert same.status_code == 200
    cleared = await patch(api, anna, first["id"], barcode=None)
    assert cleared.json()["barcode"] is None
    replaced = await patch(api, anna, second["id"], barcode=EAN_13)
    assert (replaced.json()["barcode"], replaced.json()["source"]) == (EAN_13, "manual")


async def link(api: AsyncClient, user: Account, ingredient_id: str, barcode: str) -> Any:
    return await api.post(
        f"/api/ingredients/{ingredient_id}/barcode", json={"barcode": barcode}, headers=user.headers
    )


async def test_link_a_barcode_to_an_ingredient_without_one(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    """The scanner's "already in MealMate" (BAR-03): the ingredient gets the scanned barcode
    and stays manual."""
    eggs = await create_ingredient(api, anna, "Eier", brand="REWE")
    clock.advance(minutes=5)

    response = await link(api, ben, eggs["id"], f" {UPC_A} ")

    assert response.status_code == 200
    body = response.json()
    assert (body["barcode"], body["source"], body["user_edited_fields"]) == (
        f"0{UPC_A}",
        "manual",
        [],
    )
    assert (body["name"], body["brand"]) == ("Eier", "REWE")
    assert (body["updated_by"], body["updated_at"]) == (ref(ben), "2026-09-27T12:05:00Z")
    assert (await get(api, anna, eggs["id"]))["barcode"] == f"0{UPC_A}"


async def test_linking_never_replaces_a_barcode(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    """Refused by the server, not only hidden in the picker, whose list may be stale: 409
    `ingredient.has_barcode` (also for the same barcode), 409 `ingredient.barcode_taken` if
    another ingredient has it."""
    pasta = await create_ingredient(api, anna, "Nudeln", barcode=EAN_13)
    rice = await create_ingredient(api, anna, "Reis")

    for barcode in (EAN_13_B, EAN_13):
        has = await link(api, anna, pasta["id"], barcode)
        assert has.status_code == 409
        assert error(has) == "ingredient.has_barcode"
    taken = await link(api, anna, rice["id"], EAN_13)
    assert taken.status_code == 409
    assert error(taken) == "ingredient.barcode_taken"
    assert taken.json()["params"] == {"ingredient_id": pasta["id"]}
    invalid = await link(api, anna, rice["id"], "123")
    assert fields(invalid) == {("body", "barcode"): "invalid_format"}
    missing = await link(api, anna, "unknown", EAN_13_B)
    assert missing.status_code == 404
    assert await scalars(app, select(Ingredient.barcode).order_by(Ingredient.name)) == [
        EAN_13,
        None,
    ]


# --- from Open Food Facts in one request (BAR-03, BAR-04) --------------------------------------


async def test_create_from_open_food_facts(
    api: AsyncClient, anna: Account, clock: FakeClock
) -> None:
    body = await create_from_off(
        api,
        anna,
        "Haferflocken",
        "2000000000015",
        brand="MealMate Test Kitchen",
        quantity_text="500 g",
        pack_quantity=500,
        pack_unit="g",
        nutrients={"kcal": 370, "protein": 13.5},
        edited_fields=["nutrients.kcal", "name", "name"],
        off_last_modified_at="2026-01-01T00:00:00Z",
    )
    assert body["source"] == "off"
    assert body["barcode"] == "2000000000015"
    # The pack size, passed on from the proposal (D-38).
    assert (body["quantity_text"], body["pack_quantity"], body["pack_unit"]) == ("500 g", 500, "g")
    # Only the fields the user changed compared with the proposal, in field order.
    assert body["user_edited_fields"] == ["name", "nutrients.kcal"]
    assert body["off_last_modified_at"] == "2026-01-01T00:00:00Z"
    assert body["fetched_at"] == "2026-09-27T12:00:00Z"
    assert body["pending_update"] is None


@pytest.mark.parametrize(
    "pack",
    [{"quantity_text": "500 g"}, {"pack_quantity": 500}, {"pack_unit": "g"}, {"pack_unit": None}],
)
async def test_the_pack_size_needs_an_open_food_facts_origin(
    api: AsyncClient, anna: Account, pack: dict[str, Any]
) -> None:
    """The pack size is Open Food Facts' alone (ING-02, D-38): typed by hand, it is refused."""
    response = await post(api, anna, name="Haferflocken", barcode=EAN_13, **pack)
    assert response.status_code == 422
    assert fields(response) == {("body", field): "invalid" for field in pack}


@pytest.mark.parametrize(
    ("pack", "field", "code"),
    [
        ({"quantity_text": "x" * 41}, "quantity_text", "too_long"),
        ({"quantity_text": "500͸ g"}, "quantity_text", "invalid_format"),
        ({"pack_quantity": 0}, "pack_quantity", "out_of_range"),
        ({"pack_quantity": 100_001}, "pack_quantity", "out_of_range"),
        ({"pack_unit": "cup"}, "pack_unit", "invalid"),
    ],
)
async def test_invalid_pack_sizes(
    api: AsyncClient, anna: Account, pack: dict[str, Any], field: str, code: str
) -> None:
    off = {"edited_fields": []}
    response = await post(api, anna, name="Haferflocken", barcode=EAN_13, off=off, **pack)
    assert response.status_code == 422
    assert fields(response) == {("body", field): code}


async def test_the_pack_size_is_never_edited(api: AsyncClient, anna: Account) -> None:
    """Not even an edited pack size from the proposal is marked (BAR-04)."""
    response = await post(
        api,
        anna,
        name="Haferflocken",
        barcode=EAN_13,
        quantity_text="1 kg",
        off={"edited_fields": ["quantity_text"]},
    )
    assert fields(response) == {("body", "off", "edited_fields", 0): "invalid"}


async def test_from_open_food_facts_needs_a_barcode(api: AsyncClient, anna: Account) -> None:
    response = await post(api, anna, name="Haferflocken", off={"edited_fields": []})
    assert response.status_code == 422
    assert fields(response) == {("body", "barcode"): "required"}
    unknown = await post(
        api, anna, name="Haferflocken", barcode=EAN_13, off={"edited_fields": ["barcode"]}
    )
    assert fields(unknown) == {("body", "off", "edited_fields", 0): "invalid"}


async def test_editing_an_off_ingredient_marks_the_fields(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    oats = await create_from_off(
        api, anna, "Haferflocken", EAN_13, brand="Kölln", nutrients={"fat": 7}
    )
    clock.advance(minutes=10)

    response = await patch(
        api,
        ben,
        oats["id"],
        name="Zarte Haferflocken",
        brand=None,
        nutrients={"kcal": 372, "fat": None},
        base_unit="piece",
        piece_weight_g=1,
        category_id=oats["category_id"],
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["brand"]) == ("Zarte Haferflocken", None)
    assert body["nutrients"] == NO_NUTRIENTS | {"kcal": 372}
    # Only Open Food Facts fields are marked (not the base unit, piece weight or category).
    assert body["user_edited_fields"] == ["name", "brand", "nutrients.kcal", "nutrients.fat"]
    assert (body["created_by"], body["updated_by"]) == (ref(anna), ref(ben))
    assert body["updated_at"] == "2026-09-27T12:10:00Z"


@pytest.mark.parametrize(
    "pack",
    [
        {"quantity_text": "1 kg"},
        {"pack_quantity": 1000},
        {"pack_unit": "kg"},
        {"quantity_text": None, "pack_quantity": None, "pack_unit": None},
    ],
)
async def test_the_pack_size_is_refused_on_update(
    api: AsyncClient, anna: Account, pack: dict[str, Any]
) -> None:
    """Never edited, so never user-edited (BAR-04, D-38): sent anyway, it is refused, not
    ignored, and nothing changes."""
    oats = await create_from_off(
        api, anna, "Haferflocken", EAN_13, quantity_text="500 g", pack_quantity=500, pack_unit="g"
    )
    response = await patch(api, anna, oats["id"], name="Hafer", **pack)
    assert response.status_code == 422
    assert fields(response) == {("body", field): "invalid" for field in pack}
    assert await get(api, anna, oats["id"]) == oats


def open_food_facts_data(body: dict[str, Any]) -> tuple[Any, ...]:
    return (
        body["source"],
        body["user_edited_fields"],
        body["off_last_modified_at"],
        body["fetched_at"],
        body["pending_update"],
    )


@pytest.mark.parametrize("barcode", [None, EAN_13_B])
async def test_clearing_or_changing_the_barcode_makes_it_manual(
    app: FastAPI, api: AsyncClient, anna: Account, barcode: str | None
) -> None:
    """Else a refresh would fetch the new barcode and overwrite the name, brand, pack and
    nutrients with another product's data; the values stay as they are."""
    oats = await create_from_off(
        api,
        anna,
        "Haferflocken",
        EAN_13,
        brand="Kölln",
        nutrients={"kcal": 370},
        edited_fields=["name"],
        off_last_modified_at="2026-01-01T00:00:00Z",
    )
    database = app.state.database
    async with database.write_sessions() as session, session.begin():
        row = await session.get(Ingredient, oats["id"])
        assert row is not None
        row.ignored_off_modified_at = row.off_last_modified_at
        row.pending_update = {"brand": {"current": "Kölln", "proposed": "Kölln Flocken"}}
    assert (await get(api, anna, oats["id"]))["pending_update"] is not None

    body = (await patch(api, anna, oats["id"], barcode=barcode)).json()

    assert body["barcode"] == barcode
    assert open_food_facts_data(body) == ("manual", [], None, None, None)
    assert (body["name"], body["brand"], body["nutrients"]["kcal"]) == (
        "Haferflocken",
        "Kölln",
        370,
    )
    assert await scalars(app, select(Ingredient.ignored_off_modified_at)) == [None]
    # Editing a manual ingredient marks nothing.
    assert (await patch(api, anna, oats["id"], name="Hafer")).json()["user_edited_fields"] == []


async def test_the_same_barcode_keeps_it_from_open_food_facts(
    api: AsyncClient, anna: Account
) -> None:
    """The edit form sends the barcode unchanged (in any spelling) with every save."""
    oats = await create_from_off(
        api, anna, "Haferflocken", EAN_13, off_last_modified_at="2026-01-01T00:00:00Z"
    )
    body = (await patch(api, anna, oats["id"], barcode=f" {EAN_13} ", name="Hafer")).json()
    assert open_food_facts_data(body) == (
        "off",
        ["name"],
        "2026-01-01T00:00:00Z",
        "2026-09-27T12:00:00Z",
        None,
    )


# --- search and the similar hint (ING-03) ------------------------------------------------------


async def test_search_ignores_case_umlauts_and_accents(api: AsyncClient, anna: Account) -> None:
    for name in ("Äpfel", "Crème fraîche", "Birnen", "Apfelmus"):
        await create_ingredient(api, anna, name)

    for query in ("apfel", "Äpfel", "aepfel", "ÄPF"):
        assert "Äpfel" in await search(api, anna, q=query), query
    # "aepfel" and "apfel" are the same search (ING-03); the exact name comes first.
    assert await search(api, anna, q="aepfel") == ["Äpfel", "Apfelmus"]
    assert await search(api, anna, q="creme") == ["Crème fraîche"]
    assert await search(api, anna, q="FRAICHE") == ["Crème fraîche"]
    assert await search(api, anna, q="zzz") == []


async def test_search_order(api: AsyncClient, anna: Account) -> None:
    """The exact name first, then names starting with the query, then by name and brand."""
    for name, brand in (
        ("Passierte Tomaten", "Mutti"),
        ("Tomatenmark", None),
        ("Tomaten", "Mutti"),
        ("Getrocknete Tomaten", None),
        ("Tomaten", None),
        ("Tomaten", "Alnatura"),
    ):
        await create_ingredient(api, anna, name, brand=brand)
    assert await search(api, anna, q="tomaten") == [
        "Tomaten",
        "Tomaten (Alnatura)",
        "Tomaten (Mutti)",
        "Tomatenmark",
        "Getrocknete Tomaten",
        "Passierte Tomaten (Mutti)",
    ]
    assert (await search(api, anna, q="toma"))[:4] == [
        "Tomaten",
        "Tomaten (Alnatura)",
        "Tomaten (Mutti)",
        "Tomatenmark",
    ]


async def test_search_by_brand(api: AsyncClient, anna: Account) -> None:
    await create_ingredient(api, anna, "Milch", brand="Weihenstephan")
    await create_ingredient(api, anna, "Butter", brand="Weihenstephan")
    await create_ingredient(api, anna, "Milch", brand="Müller")
    await create_ingredient(api, anna, "Weißwurst")

    assert await search(api, anna, q="weihenstephan") == [
        "Butter (Weihenstephan)",
        "Milch (Weihenstephan)",
    ]
    assert await search(api, anna, q="MUELLER") == ["Milch (Müller)"]
    assert await search(api, anna, q="muller") == ["Milch (Müller)"]
    # Name and brand together.
    assert await search(api, anna, q="milch weihen") == ["Milch (Weihenstephan)"]
    # A name starting with the query first, then the brands.
    assert await search(api, anna, q="wei") == [
        "Weißwurst",
        "Butter (Weihenstephan)",
        "Milch (Weihenstephan)",
    ]


async def test_list_in_dictionary_order(api: AsyncClient, anna: Account) -> None:
    """ING-03, D-27: by name, then brand, whatever the category. Ä sorts as A, ß as ss and è as
    e; real letter pairs keep their place ("Paella" before "Pak", "Sauer" before "Saure")."""
    categories = await category_ids(api, anna)
    fruit = categories["fruit_vegetables"]
    for name, brand, category in (
        ("Salz", None, "sauces_spices_oils"),
        ("Zwiebeln", None, "fruit_vegetables"),
        ("Saure Sahne", None, "dairy_eggs"),
        ("Äpfel", None, "fruit_vegetables"),
        ("Pak Choi", None, "fruit_vegetables"),
        ("Milch", "Müller", "dairy_eggs"),
        ("Alufolie", None, "other"),
        ("Sauerkraut", None, "canned_jars"),
        ("Milch", None, "dairy_eggs"),
        ("Apfelessig", None, "sauces_spices_oils"),
        ("Paella-Reis", None, "pasta_rice_grains"),
        ("Milch", "MUH", "dairy_eggs"),
        ("Weizenmehl", None, "baking"),
        ("Croissant", None, "bread_bakery"),
        ("Ananas", None, "fruit_vegetables"),
        ("Weißkohl", None, "fruit_vegetables"),
        ("Crème fraîche", None, "dairy_eggs"),
    ):
        await create_ingredient(api, anna, name, brand=brand, category_id=categories[category])

    assert await search(api, anna) == [
        "Alufolie",
        "Ananas",
        "Äpfel",
        "Apfelessig",
        "Crème fraîche",
        "Croissant",
        "Milch",
        "Milch (MUH)",
        "Milch (Müller)",
        "Paella-Reis",
        "Pak Choi",
        "Salz",
        "Sauerkraut",
        "Saure Sahne",
        "Weißkohl",
        "Weizenmehl",
        "Zwiebeln",
    ]
    assert await search(api, anna, q="  ") == await search(api, anna)
    assert await search(api, anna, category_id=fruit) == [
        "Ananas",
        "Äpfel",
        "Pak Choi",
        "Weißkohl",
        "Zwiebeln",
    ]
    assert await search(api, anna, category_id=fruit, q="zw") == ["Zwiebeln"]
    assert await search(api, anna, category_id="unknown") == []


async def test_list_of_several_categories(api: AsyncClient, anna: Account) -> None:
    """ING-03, UI-01, D-23: several categories match any of them, in one list in dictionary
    order; a search narrows them down. An unknown category adds nothing."""
    categories = await category_ids(api, anna)
    fruit, dairy = categories["fruit_vegetables"], categories["dairy_eggs"]
    for name, category in (
        ("Zwiebeln", "fruit_vegetables"),
        ("Salz", "sauces_spices_oils"),
        ("Milch", "dairy_eggs"),
        ("Äpfel", "fruit_vegetables"),
        ("Butter", "dairy_eggs"),
        ("Alufolie", "other"),
    ):
        await create_ingredient(api, anna, name, category_id=categories[category])

    both = ["Äpfel", "Butter", "Milch", "Zwiebeln"]
    assert await search(api, anna, category_id=[fruit, dairy]) == both
    assert await search(api, anna, category_id=[dairy, fruit, "unknown"]) == both
    assert await search(api, anna, category_id=[fruit, dairy], q="i") == ["Milch", "Zwiebeln"]
    assert await search(api, anna, category_id=[fruit, fruit]) == ["Äpfel", "Zwiebeln"]


async def test_renaming_moves_the_ingredient(api: AsyncClient, anna: Account) -> None:
    await create_ingredient(api, anna, "Apfelessig")
    apples = await create_ingredient(api, anna, "Bratäpfel")
    await create_ingredient(api, anna, "Milch", brand="MUH")
    milk = await create_ingredient(api, anna, "Milch", brand="Alnatura")

    assert (await patch(api, anna, apples["id"], name="Äpfel")).status_code == 200
    assert (await patch(api, anna, milk["id"], brand="Müller")).status_code == 200

    assert await search(api, anna) == ["Äpfel", "Apfelessig", "Milch (MUH)", "Milch (Müller)"]


async def test_search_ranks_then_dictionary_order(api: AsyncClient, anna: Account) -> None:
    """ING-03: the best matches first ("Milch" above "Buttermilch"), each rank in dictionary
    order."""
    for name, brand in (
        ("Buttermilch", None),
        ("Milch", "Müller"),
        ("Milchreis", None),
        ("Milch", "MUH"),
        ("Milch", None),
        ("Pflaumenmus", None),
        ("Müsli", None),
        ("Hummus", None),
        ("Muskatnuss", None),
        ("Apfelmus", None),
    ):
        await create_ingredient(api, anna, name, brand=brand)

    assert await search(api, anna, q="milch") == [
        "Milch",
        "Milch (MUH)",
        "Milch (Müller)",
        "Milchreis",
        "Buttermilch",
    ]
    assert await search(api, anna, q="mus") == [
        "Muskatnuss",
        "Müsli",
        "Apfelmus",
        "Hummus",
        "Pflaumenmus",
    ]


async def test_summaries(api: AsyncClient, anna: Account) -> None:
    milk = await create_from_off(api, anna, "Milch", EAN_13, brand="Weihenstephan", base_unit="ml")
    response = await api.get("/api/ingredients", params={"q": "milch"}, headers=anna.headers)
    assert response.json() == [
        {
            "id": milk["id"],
            "name": "Milch",
            "brand": "Weihenstephan",
            "barcode": EAN_13,
            "source": "off",
            "category_id": milk["category_id"],
            "base_unit": "ml",
        }
    ]


async def similar(api: AsyncClient, user: Account, name: str, **params: str) -> list[str]:
    response = await api.get(
        "/api/ingredients/similar", params={"name": name, **params}, headers=user.headers
    )
    assert response.status_code == 200
    return [
        item["name"] if item["brand"] is None else f"{item['name']} ({item['brand']})"
        for item in response.json()
    ]


async def test_similar_ingredients(api: AsyncClient, anna: Account) -> None:
    for name in ("Äpfel", "Apfelmus", "Birnen", "Tomaten", "Tomate getrocknet"):
        await create_ingredient(api, anna, name)

    assert await similar(api, anna, "Apfel") == ["Äpfel", "Apfelmus"]
    assert await similar(api, anna, "äpfel") == ["Äpfel", "Apfelmus"]
    assert await similar(api, anna, "Tomate") == ["Tomaten", "Tomate getrocknet"]
    assert await similar(api, anna, "Birne") == ["Birnen"]
    assert await similar(api, anna, "Gurke") == []
    assert await similar(api, anna, "  ") == []
    response = await api.get("/api/ingredients/similar", headers=anna.headers)
    assert fields(response) == {("query", "name"): "required"}


async def test_the_same_name_and_brand_come_first(api: AsyncClient, anna: Account) -> None:
    for brand in (None, "Landliebe", "Weihenstephan"):
        await create_ingredient(api, anna, "Milch", brand=brand)
    await create_ingredient(api, anna, "Milchreis")

    assert await similar(api, anna, "milch", brand="WEIHENSTEPHAN") == [
        "Milch (Weihenstephan)",
        "Milch",
        "Milch (Landliebe)",
        "Milchreis",
    ]
    assert (await similar(api, anna, "Milch"))[0] == "Milch"


async def test_at_most_five_similar_ingredients(api: AsyncClient, anna: Account) -> None:
    for i in range(7):
        await create_ingredient(api, anna, f"Tee {i}")
    assert await similar(api, anna, "Tee") == [f"Tee {i}" for i in range(5)]


# --- editing (ING-01, ING-02) ------------------------------------------------------------------


async def test_anyone_edits_and_is_recorded(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    categories = await category_ids(api, anna)
    apples = await create_ingredient(
        api, anna, "Apfel", base_unit="piece", piece_weight_g=180, nutrients={"kcal": 52}
    )
    clock.advance(minutes=5)

    response = await patch(
        api,
        ben,
        apples["id"],
        name="Äpfel",
        brand="Bio",
        category_id=categories["fruit_vegetables"],
        piece_weight_g=None,
        nutrients={"protein": 0.3, "kcal": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["brand"]) == ("Äpfel", "Bio")
    assert body["category_id"] == categories["fruit_vegetables"]
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", None)
    assert body["nutrients"] == NO_NUTRIENTS | {"protein": 0.3}
    assert body["user_edited_fields"] == []
    assert body["created_by"] == ref(anna)
    assert body["updated_by"] == ref(ben)
    assert body["created_at"] == "2026-09-27T12:00:00Z"
    assert body["updated_at"] == "2026-09-27T12:05:00Z"
    assert await get(api, anna, apples["id"]) == body
    assert await search(api, anna, q="bio") == ["Äpfel (Bio)"]


async def test_renaming_to_an_existing_name_is_fine(api: AsyncClient, anna: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    await create_ingredient(api, anna, "Birnen")
    assert (await patch(api, anna, apples["id"], name="birnen")).json()["name"] == "birnen"
    response = await patch(api, anna, apples["id"], category_id="nope")
    assert fields(response) == {("body", "category_id"): "invalid"}


async def test_the_base_unit_changes_freely(api: AsyncClient, anna: Account) -> None:
    """Nothing is converted: the values are per 100 of the new base unit from now on."""
    oil = await create_ingredient(api, anna, "Olivenöl", barcode=EAN_13, nutrients={"fat": 92})
    body = (await patch(api, anna, oil["id"], base_unit="ml")).json()
    assert (body["base_unit"], body["nutrients"]["fat"]) == ("ml", 92)


# --- base unit Stück (ING-02, D-32) -----------------------------------------------------------


async def test_a_piece_ingredient_with_a_piece_weight(api: AsyncClient, anna: Account) -> None:
    eggs = await create_ingredient(
        api, anna, "Eier", base_unit="piece", piece_weight_g=60, nutrients={"kcal": 155}
    )
    assert (eggs["base_unit"], eggs["piece_weight_g"], eggs["nutrients"]["kcal"]) == (
        "piece",
        60,
        155,
    )
    assert await get(api, anna, eggs["id"]) == eggs
    response = await api.get("/api/ingredients", params={"q": "eier"}, headers=anna.headers)
    assert [(item["name"], item["base_unit"]) for item in response.json()] == [("Eier", "piece")]

    body = (await patch(api, anna, eggs["id"], piece_weight_g=10_000)).json()
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", 10_000)
    body = (await patch(api, anna, eggs["id"], piece_weight_g=None)).json()
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", None)
    without = await create_ingredient(api, anna, "Brötchen", base_unit="piece")
    assert (without["base_unit"], without["piece_weight_g"]) == ("piece", None)


async def test_counting_an_ingredient_in_pieces(api: AsyncClient, anna: Account) -> None:
    """Nothing is converted: the values are per 100 g as before; a piece weight comes along."""
    rolls = await create_ingredient(api, anna, "Brötchen", nutrients={"kcal": 270})
    body = (await patch(api, anna, rolls["id"], base_unit="piece", piece_weight_g=50)).json()
    assert (body["base_unit"], body["piece_weight_g"], body["nutrients"]["kcal"]) == (
        "piece",
        50,
        270,
    )


@pytest.mark.parametrize("base_unit", ["g", "ml"])
async def test_leaving_pieces_clears_the_piece_weight(
    api: AsyncClient, anna: Account, base_unit: str
) -> None:
    eggs = await create_ingredient(api, anna, "Eier", base_unit="piece", piece_weight_g=60)
    assert (await patch(api, anna, eggs["id"], name="Eier (M)")).json()["piece_weight_g"] == 60
    same = (await patch(api, anna, eggs["id"], base_unit="piece")).json()
    assert same["piece_weight_g"] == 60

    body = (await patch(api, anna, eggs["id"], base_unit=base_unit)).json()
    assert (body["base_unit"], body["piece_weight_g"]) == (base_unit, None)
    # Back to pieces, it has none.
    body = (await patch(api, anna, eggs["id"], base_unit="piece")).json()
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", None)

    # One sent along is refused: a g or ml ingredient has none (D-32).
    again = await create_ingredient(api, anna, "Eier", base_unit="piece", piece_weight_g=60)
    response = await patch(api, anna, again["id"], base_unit=base_unit, piece_weight_g=55)
    assert fields(response) == {("body", "piece_weight_g"): "invalid"}
    assert (await get(api, anna, again["id"]))["piece_weight_g"] == 60


# --- a base-unit change that leaves amounts not fitting (ING-02, D-33) ------------------------


def amount(ingredient: Any, value: float | None = None, unit: str | None = None) -> Any:
    """A meal row of the ingredient."""
    return {"ingredient_id": ingredient["id"], "amount": value, "unit": unit}


async def meal_amounts(api: AsyncClient, user: Account, meal_id: str) -> list[Any]:
    """A meal's rows as `(amount, unit, unit_fits)`."""
    response = await api.get(f"/api/meals/{meal_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return [
        (row["amount"], row["unit"], row["unit_fits"]) for row in response.json()["ingredients"]
    ]


async def extra_amounts(api: AsyncClient, user: Account, list_id: str) -> list[Any]:
    """A list's extra items as `(amount, unit, unit_fits)`."""
    body = await detail(api, user, list_id)
    return [(item["amount"], item["unit"], item["unit_fits"]) for item in body["extra_items"]]


async def test_a_base_unit_change_that_leaves_amounts_not_fitting_asks_first(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    """Counted are the meals with rows, and the drafts with linked extra items, whose amounts fit
    now and wouldn't fit the new base unit. Nothing is saved until the request accepts that, and
    then nothing is converted: those amounts are kept and flagged."""
    eggs = await create_ingredient(api, anna, "Eier")
    flour = await create_ingredient(api, anna, "Mehl")
    omelette = await create_meal(
        api, anna, "Omelett", ingredients=[amount(eggs, 120, "g"), amount(eggs, 1, "tbsp")]
    )
    cake = await create_meal(
        api, ben, "Kuchen", ingredients=[amount(flour, 500, "g"), amount(eggs, 0.2, "kg")]
    )
    # A row without an amount fits every base unit.
    await create_meal(api, ben, "Pfannkuchen", ingredients=[amount(eggs), amount(flour, 250, "g")])
    draft = await create_list(api, anna)
    await extra_added(api, anna, draft["id"], ingredient_id=eggs["id"], amount=500, unit="g")
    await extra_added(api, anna, draft["id"], ingredient_id=eggs["id"])
    other_draft = await create_list(api, ben)
    await extra_added(api, ben, other_draft["id"], ingredient_id=eggs["id"])
    before = await get(api, anna, eggs["id"])
    clock.advance(minutes=1)

    response = await patch(api, ben, eggs["id"], base_unit="piece", name="Eier (M)")

    assert response.status_code == 409
    assert error(response) == "ingredient.unit_mismatch"
    assert response.json()["params"] == {"meals": 2, "lists": 1, "amounts": 4}
    assert await get(api, anna, eggs["id"]) == before

    response = await patch(
        api, ben, eggs["id"], base_unit="piece", name="Eier (M)", accept_unit_mismatch=True
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["base_unit"], body["updated_by"]) == ("Eier (M)", "piece", ref(ben))
    assert await meal_amounts(api, anna, omelette["id"]) == [(120, "g", False), (1, "tbsp", False)]
    assert await meal_amounts(api, ben, cake["id"]) == [(500, "g", True), (0.2, "kg", False)]
    assert await extra_amounts(api, anna, draft["id"]) == [(500, "g", False), (None, None, True)]


async def test_a_base_unit_change_no_amount_depends_on_asks_nothing(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    """Spoons fit g and ml alike, a row without an amount fits every base unit, and an amount
    that doesn't fit already (D-33) can't stop fitting; accepting is fine when nothing would."""
    flour = await create_ingredient(api, anna, "Mehl")
    rolls = await create_ingredient(api, anna, "Brötchen", base_unit="piece")
    meal = await create_meal(
        api, anna, "Brot", ingredients=[amount(flour, 2, "tbsp"), amount(flour), amount(rolls, 2)]
    )
    # Counted in grams since before D-33, so its pieces don't fit.
    await set_stored(app, rolls["id"], base_unit="g")

    for ingredient, base_unit, accept in (
        (flour, "ml", False),
        (rolls, "ml", False),
        (rolls, "piece", False),
        (rolls, "g", True),
    ):
        body: dict[str, Any] = {"base_unit": base_unit}
        if accept:
            body["accept_unit_mismatch"] = True
        response = await patch(api, anna, ingredient["id"], **body)
        assert response.status_code == 200, (base_unit, response.text)
        assert response.json()["base_unit"] == base_unit
    assert await meal_amounts(api, anna, meal["id"]) == [
        (2, "tbsp", True),
        (None, None, True),
        (2, "piece", False),
    ]


async def test_lists_being_shopped_and_done_lists_do_not_count(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    """LIST-11, D-08: their linked extra items keep the base unit they copied when shopping
    started, so a base-unit change neither asks about them nor changes them."""
    eggs = await create_ingredient(api, anna, "Eier")
    shopping, done = await create_list(api, anna, "Einkauf"), await create_list(api, anna, "Fertig")
    for shopping_list, grams in ((shopping, 500), (done, 250)):
        await extra_added(
            api, anna, shopping_list["id"], ingredient_id=eggs["id"], amount=grams, unit="g"
        )
        await start_shopping(api, anna, shopping_list["id"])
    await set_status(app, done["id"], "done")
    lists = [await detail(api, anna, item["id"]) for item in (shopping, done)]

    response = await patch(api, anna, eggs["id"], base_unit="piece")

    assert response.status_code == 200, response.text
    after = [await detail(api, anna, item["id"]) for item in (shopping, done)]
    for old, new in zip(lists, after, strict=True):
        assert (new["lines"], new["extra_items"]) == (old["lines"], old["extra_items"])
        assert [item["unit_fits"] for item in new["extra_items"]] == [True]


async def test_invalid_updates(api: AsyncClient, anna: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    response = await patch(api, anna, apples["id"], name="", nutrients={"fat": 101})
    assert fields(response) == {
        ("body", "name"): "too_short",
        ("body", "nutrients", "fat"): "out_of_range",
    }


async def test_null_is_refused_for_required_fields(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    clock.advance(minutes=1)
    response = await patch(api, ben, apples["id"], name=None, category_id=None, base_unit=None)
    assert response.status_code == 422
    assert error(response) == "common.validation"
    assert fields(response) == {
        ("body", "name"): "invalid",
        ("body", "category_id"): "invalid",
        ("body", "base_unit"): "invalid",
    }
    for field in ("name", "category_id", "base_unit"):
        alone = await patch(api, ben, apples["id"], **{field: None})
        assert fields(alone) == {("body", field): "invalid"}
    assert await get(api, anna, apples["id"]) == apples


async def test_an_empty_update_only_records_the_editor(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel", base_unit="piece", piece_weight_g=180)
    clock.advance(minutes=1)
    body = (await patch(api, ben, apples["id"])).json()
    changed = {"updated_by": None, "updated_at": None}
    assert body | changed == apples | changed
    assert body["updated_at"] == "2026-09-27T12:01:00Z"
    assert body["updated_by"] == ref(ben)


async def test_deleted_creator(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, admin: Account
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel", base_unit="piece")
    await patch(api, ben, apples["id"], piece_weight_g=180)
    assert (
        await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)
    ).status_code == 204

    body = await get(api, ben, apples["id"])

    assert body["created_by"] is None
    assert body["updated_by"] == ref(ben)
    assert await scalars(app, select(Ingredient.name)) == ["Äpfel"]


async def test_usage(api: AsyncClient, anna: Account, ben: Account) -> None:
    rice = await create_ingredient(api, anna, "Reis")
    rows = [{"ingredient_id": rice["id"], "amount": 100, "unit": "g"}] * 2
    await create_meal(api, anna, "Risotto", ingredients=rows)
    await create_meal(api, ben, "Reispfanne", ingredients=rows[:1])
    shopping_list = await create_list(api, anna)
    await extra_added(api, anna, shopping_list["id"], ingredient_id=rice["id"])
    assert (await get(api, ben, rice["id"]))["usage"] == {"meals": 2, "lists": 1}


# --- merge and delete (ING-05, admins) ---------------------------------------------------------


async def merge(
    api: AsyncClient, user: Account, ingredient_id: str, into_id: str, **body: Any
) -> Any:
    return await api.post(
        f"/api/admin/ingredients/{ingredient_id}/merge",
        json={"into_id": into_id, **body},
        headers=user.headers,
    )


async def events(api: AsyncClient, admin: Account) -> list[tuple[str, dict[str, Any]]]:
    response = await api.get("/api/admin/events", headers=admin.headers)
    return [(event["action"], event["details"]) for event in response.json()]


async def test_merge(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    admin: Account,
    monkeypatch: pytest.MonkeyPatch,
    clock: FakeClock,
) -> None:
    calls: list[tuple[str, str]] = []

    async def on_ingredients_merged(
        _session: object, from_id: str, into_id: str, **_: object
    ) -> None:
        calls.append((from_id, into_id))

    monkeypatch.setattr(hooks, "on_ingredients_merged", on_ingredients_merged)
    duplicate = await create_ingredient(api, anna, "Paradeiser", nutrients={"kcal": 20})
    tomatoes = await create_ingredient(api, anna, "Tomaten", piece_weight_g=100, base_unit="piece")
    clock.advance(minutes=10)

    response = await merge(api, admin, duplicate["id"], tomatoes["id"])

    assert response.status_code == 200
    body = response.json()
    # The target keeps its own attributes and values; different base units do not matter.
    assert (body["id"], body["name"], body["piece_weight_g"]) == (tomatoes["id"], "Tomaten", 100)
    assert body["nutrients"] == NO_NUTRIENTS
    assert (body["created_by"], body["updated_by"]) == (ref(anna), ref(admin))
    assert body["updated_at"] == "2026-09-27T12:10:00Z"
    assert calls == [(duplicate["id"], tomatoes["id"])]
    assert await scalars(app, select(Ingredient.name)) == ["Tomaten"]
    missing = await api.get(f"/api/ingredients/{duplicate['id']}", headers=anna.headers)
    assert missing.status_code == 404
    assert await events(api, admin) == [
        ("ingredient.merge", {"from_name": "Paradeiser", "into_name": "Tomaten"})
    ]


async def test_merge_moves_the_barcode_to_a_target_without_one(
    api: AsyncClient, anna: Account, admin: Account
) -> None:
    scanned = await create_from_off(api, anna, "Nudeln", EAN_13, brand="Barilla")
    generic = await create_ingredient(api, anna, "Spaghetti")

    body = (await merge(api, admin, scanned["id"], generic["id"])).json()

    # Only the barcode moves: the target's values and source stay.
    assert (body["barcode"], body["brand"], body["source"]) == (EAN_13, None, "manual")
    lookup = await api.get(
        "/api/ingredients/lookup", params={"barcode": EAN_13}, headers=anna.headers
    )
    assert lookup.json()["ingredient"]["id"] == generic["id"]


async def test_merge_drops_the_barcode_when_the_target_has_one(
    app: FastAPI, api: AsyncClient, anna: Account, admin: Account
) -> None:
    first = await create_ingredient(api, anna, "Nudeln", barcode=EAN_13)
    second = await create_ingredient(api, anna, "Spaghetti", barcode=EAN_8)

    body = (await merge(api, admin, first["id"], second["id"])).json()

    assert body["barcode"] == EAN_8
    assert await scalars(app, select(Ingredient.barcode)) == [EAN_8]


async def test_invalid_merges(api: AsyncClient, anna: Account, admin: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")

    itself = await merge(api, admin, apples["id"], apples["id"])
    assert fields(itself) == {("body", "into_id"): "invalid"}
    unknown_target = await merge(api, admin, apples["id"], "nope")
    assert fields(unknown_target) == {("body", "into_id"): "invalid"}
    unknown_source = await merge(api, admin, "nope", apples["id"])
    assert unknown_source.status_code == 404
    assert error(unknown_source) == "common.not_found"
    missing = await api.post(
        f"/api/admin/ingredients/{apples['id']}/merge", json={}, headers=admin.headers
    )
    assert fields(missing) == {("body", "into_id"): "required"}


async def test_delete(app: FastAPI, api: AsyncClient, anna: Account, admin: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel", barcode=EAN_13)

    response = await api.delete(f"/api/admin/ingredients/{apples['id']}", headers=admin.headers)

    assert response.status_code == 204
    assert await scalars(app, select(Ingredient.id)) == []
    assert await events(api, admin) == [("ingredient.delete", {"name": "Äpfel"})]
    again = await api.delete(f"/api/admin/ingredients/{apples['id']}", headers=admin.headers)
    assert again.status_code == 404


async def test_ingredients_in_use_are_not_deleted(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, admin: Account
) -> None:
    rice = await create_ingredient(api, anna, "Reis")
    rows = [{"ingredient_id": rice["id"], "amount": 100, "unit": "g"}] * 2
    await create_meal(api, anna, "Risotto", ingredients=rows)
    await create_meal(api, ben, "Reispfanne", ingredients=rows[:1])

    response = await api.delete(f"/api/admin/ingredients/{rice['id']}", headers=admin.headers)
    assert response.status_code == 409
    assert error(response) == "ingredient.in_use"
    assert response.json()["params"] == {"meals": 2, "lists": 0}
    assert len(await scalars(app, select(Ingredient.id))) == 1
    assert await scalars(app, select(AdminEvent.id)) == []


async def test_merging_moves_meal_rows_and_list_lines(
    api: AsyncClient, anna: Account, admin: Account
) -> None:
    duplicate = await create_ingredient(api, anna, "Paradeiser")
    tomatoes = await create_ingredient(api, anna, "Tomaten", base_unit="piece")
    salt = await create_ingredient(api, anna, "Salz")
    meal = await create_meal(
        api,
        anna,
        "Salat",
        ingredients=[
            {"ingredient_id": tomatoes["id"], "amount": 2, "unit": "piece"},
            {"ingredient_id": salt["id"]},
            {"ingredient_id": duplicate["id"], "amount": 200, "unit": "g"},
        ],
    )
    shopping_list = await create_list(api, anna)
    await extra_added(api, anna, shopping_list["id"], ingredient_id=duplicate["id"])

    response = await merge(api, admin, duplicate["id"], tomatoes["id"], accept_unit_mismatch=True)
    assert response.status_code == 200, response.text

    response = await api.get(f"/api/meals/{meal['id']}", headers=anna.headers)
    rows = [
        (row["id"], row["ingredient"]["id"], row["unit_fits"])
        for row in response.json()["ingredients"]
    ]
    # Nothing is converted: 200 g of the merged ingredient don't fit Tomaten (D-33).
    assert rows == [
        (meal["ingredients"][0]["id"], tomatoes["id"], True),
        (meal["ingredients"][1]["id"], salt["id"], True),
        (meal["ingredients"][2]["id"], tomatoes["id"], False),
    ]
    lines = (await detail(api, anna, shopping_list["id"]))["lines"]
    assert [line["key"] for line in lines] == [f"i:{tomatoes['id']}"]


async def test_a_merge_across_base_units_names_the_amounts_that_wont_fit(
    app: FastAPI, api: AsyncClient, anna: Account, admin: Account
) -> None:
    """ING-05, D-33: counted are the duplicate's amounts (meal rows, and linked extra items on
    drafts) that won't fit the ingredient that stays, those that didn't fit the duplicate
    either included. Nothing is merged until the request accepts that, and then nothing is
    converted."""
    duplicate = await create_ingredient(api, anna, "Ei", base_unit="ml")
    old = await create_meal(api, anna, "Eierlikör", ingredients=[amount(duplicate, 100, "ml")])
    # Counted in grams since, so its millilitres don't fit (D-33).
    await set_stored(app, duplicate["id"], base_unit="g")
    eggs = await create_ingredient(api, anna, "Eier", base_unit="piece", piece_weight_g=60)
    omelette = await create_meal(
        api,
        anna,
        "Omelett",
        ingredients=[
            amount(duplicate, 120, "g"),
            amount(duplicate, 1, "tbsp"),
            amount(duplicate),
            amount(eggs, 2),
        ],
    )
    draft = await create_list(api, anna)
    await extra_added(api, anna, draft["id"], ingredient_id=duplicate["id"], amount=0.5, unit="kg")

    response = await merge(api, admin, duplicate["id"], eggs["id"])

    assert response.status_code == 409
    assert error(response) == "ingredient.unit_mismatch"
    assert response.json()["params"] == {"meals": 2, "lists": 1, "amounts": 4}
    assert sorted(await scalars(app, select(Ingredient.name))) == ["Ei", "Eier"]
    assert await events(api, admin) == []

    response = await merge(api, admin, duplicate["id"], eggs["id"], accept_unit_mismatch=True)

    assert response.status_code == 200, response.text
    assert await scalars(app, select(Ingredient.name)) == ["Eier"]
    assert await meal_amounts(api, anna, old["id"]) == [(100, "ml", False)]
    assert await meal_amounts(api, anna, omelette["id"]) == [
        (120, "g", False),
        (1, "tbsp", False),
        (None, None, True),
        (2, "piece", True),
    ]
    assert await extra_amounts(api, anna, draft["id"]) == [(0.5, "kg", False)]


async def test_a_merge_with_nothing_that_wont_fit_asks_nothing(
    app: FastAPI, api: AsyncClient, anna: Account, admin: Account
) -> None:
    """Spoons fit g and ml alike and a row without an amount fits every base unit; within one
    base unit, amounts that don't fit already (D-33) only stay flagged."""
    sugar = await create_ingredient(api, anna, "Zucker")
    syrup = await create_ingredient(api, anna, "Zuckersirup", base_unit="ml")
    duplicate = await create_ingredient(api, anna, "Paradeiser", base_unit="piece")
    tomatoes = await create_ingredient(api, anna, "Tomaten")
    tea = await create_meal(api, anna, "Tee", ingredients=[amount(sugar, 2, "tbsp"), amount(sugar)])
    salad = await create_meal(api, anna, "Salat", ingredients=[amount(duplicate, 2)])
    await set_stored(app, duplicate["id"], base_unit="g")

    for source, target in ((sugar, syrup), (duplicate, tomatoes)):
        response = await merge(api, admin, source["id"], target["id"])
        assert response.status_code == 200, response.text
    assert await meal_amounts(api, anna, tea["id"]) == [(2, "tbsp", True), (None, None, True)]
    assert await meal_amounts(api, anna, salad["id"]) == [(2, "piece", False)]


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [("POST", "/merge", {"into_id": "x"}), ("DELETE", "", None)],
)
async def test_only_admins_merge_and_delete(
    app: FastAPI, api: AsyncClient, anna: Account, method: str, suffix: str, body: Any
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    pears = await create_ingredient(api, anna, "Birnen")
    if body is not None:
        body = {"into_id": pears["id"]}
    response = await api.request(
        method, f"/api/admin/ingredients/{apples['id']}{suffix}", json=body, headers=anna.headers
    )
    assert response.status_code == 403
    assert error(response) == "common.forbidden"
    assert len(await scalars(app, select(Ingredient.id))) == 2
