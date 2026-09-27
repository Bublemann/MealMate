"""Products entered by hand: barcode, basis, per-field user edits (ING-04, BAR-04)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.accounts import Account, FakeClock, error, fields, make_user
from tests.catalog import (
    EAN_8,
    EAN_13,
    EAN_13_B,
    NO_NUTRIENTS,
    UPC_A,
    UPC_E,
    create_ingredient,
    create_product,
    ref,
)


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def pasta(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Spaghetti")


@pytest.fixture
async def milk(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Milch", base_unit="ml")


async def post(api: AsyncClient, user: Account, **body: Any) -> Any:
    return await api.post("/api/products", json=body, headers=user.headers)


async def patch(api: AsyncClient, user: Account, product_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/products/{product_id}", json=body, headers=user.headers)


async def test_create_minimal(api: AsyncClient, anna: Account, milk: Any) -> None:
    response = await post(api, anna, barcode=" 4006381 333931 ", ingredient_id=milk["id"])

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "barcode": EAN_13,
        "ingredient_id": milk["id"],
        "nutrition_basis": "ml",
        "name": None,
        "brand": None,
        "quantity_text": None,
        "pack_quantity": None,
        "pack_unit": None,
        "nutrients": NO_NUTRIENTS,
        "source": "manual",
        "user_edited_fields": [],
        "fetched_at": None,
        "created_by": ref(anna),
        "updated_by": ref(anna),
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:00:00Z",
    }
    fetched = await api.get(f"/api/products/{body['id']}", headers=anna.headers)
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_create_with_everything(api: AsyncClient, anna: Account, pasta: Any) -> None:
    body = await create_product(
        api,
        anna,
        pasta["id"],
        EAN_13_B,
        nutrition_basis="g",
        name=" Spaghetti n.5 ",
        brand="Barilla",
        quantity_text="",
        pack_quantity=500,
        pack_unit="g",
        nutrients={"kcal": 359, "protein": 12, "sugar": None},
    )
    assert (body["name"], body["brand"], body["quantity_text"]) == (
        "Spaghetti n.5",
        "Barilla",
        None,
    )
    assert (body["pack_quantity"], body["pack_unit"]) == (500, "g")
    assert body["nutrients"] == NO_NUTRIENTS | {"kcal": 359, "protein": 12}
    assert body["user_edited_fields"] == [
        "nutrition_basis",
        "name",
        "brand",
        "pack_quantity",
        "pack_unit",
        "nutrients.kcal",
        "nutrients.protein",
    ]


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
    api: AsyncClient, anna: Account, pasta: Any, barcode: str, stored: str
) -> None:
    """Stored in one canonical form: GTIN-13, except EAN-8 (BAR-01)."""
    assert (await create_product(api, anna, pasta["id"], barcode))["barcode"] == stored


@pytest.mark.parametrize(
    ("first", "second"),
    [(UPC_A, f"0{UPC_A}"), (f"0{UPC_A}", UPC_A), (UPC_E, "042100005264"), (UPC_E, "0042100005264")],
)
async def test_one_product_in_another_form_is_taken(
    api: AsyncClient, anna: Account, pasta: Any, first: str, second: str
) -> None:
    await create_product(api, anna, pasta["id"], first)
    response = await post(api, anna, barcode=second, ingredient_id=pasta["id"])
    assert response.status_code == 422
    assert fields(response) == {("body", "barcode"): "taken"}


@pytest.mark.parametrize(
    "barcode",
    [
        "4006381333932",
        "400638133393",
        "40063813339311",
        "abc",
        "4006-381333931",
        "\uff11\uff12",
    ],
)
async def test_invalid_barcodes(api: AsyncClient, anna: Account, pasta: Any, barcode: str) -> None:
    response = await post(api, anna, barcode=barcode, ingredient_id=pasta["id"])
    assert response.status_code == 422
    assert fields(response) == {("body", "barcode"): "invalid_format"}


async def test_taken_barcode_and_unknown_ingredient(
    api: AsyncClient, anna: Account, pasta: Any
) -> None:
    await create_product(api, anna, pasta["id"], EAN_13)
    response = await post(api, anna, barcode=EAN_13, ingredient_id="nope")
    assert response.status_code == 422
    assert fields(response) == {("body", "barcode"): "taken", ("body", "ingredient_id"): "invalid"}


async def test_basis_must_match_the_base_unit(api: AsyncClient, anna: Account, milk: Any) -> None:
    response = await post(api, anna, barcode=EAN_13, ingredient_id=milk["id"], nutrition_basis="g")
    assert response.status_code == 409
    assert error(response) == "product.basis_mismatch"


@pytest.mark.parametrize(
    ("body", "loc", "code"),
    [
        ({"barcode": ""}, ("body", "barcode"), "too_short"),
        ({"barcode": "1" * 33}, ("body", "barcode"), "too_long"),
        ({"name": "x" * 121}, ("body", "name"), "too_long"),
        ({"brand": "x" * 81}, ("body", "brand"), "too_long"),
        ({"quantity_text": "x" * 41}, ("body", "quantity_text"), "too_long"),
        ({"name": "Pasta‏"}, ("body", "name"), "invalid_format"),
        ({"brand": "\x07"}, ("body", "brand"), "invalid_format"),
        ({"pack_quantity": 0}, ("body", "pack_quantity"), "out_of_range"),
        ({"pack_quantity": 100_001}, ("body", "pack_quantity"), "out_of_range"),
        ({"pack_unit": "cup"}, ("body", "pack_unit"), "invalid"),
        ({"nutrition_basis": "kg"}, ("body", "nutrition_basis"), "invalid"),
        ({"nutrients": {"kcal": 901}}, ("body", "nutrients", "kcal"), "out_of_range"),
    ],
)
async def test_invalid_fields(
    api: AsyncClient,
    anna: Account,
    pasta: Any,
    body: dict[str, Any],
    loc: tuple[str, ...],
    code: str,
) -> None:
    response = await post(api, anna, **({"barcode": EAN_13, "ingredient_id": pasta["id"]} | body))
    assert response.status_code == 422
    assert fields(response) == {loc: code}


async def test_unknown_product(api: AsyncClient, anna: Account) -> None:
    for response in (
        await api.get("/api/products/nope", headers=anna.headers),
        await patch(api, anna, "nope", name="x"),
    ):
        assert response.status_code == 404
        assert error(response) == "common.not_found"


# --- editing (BAR-04) --------------------------------------------------------------------------


async def test_every_field_sent_becomes_user_edited(
    api: AsyncClient, anna: Account, ben: Account, pasta: Any, clock: FakeClock
) -> None:
    product = await create_product(
        api, anna, pasta["id"], EAN_13, name="Spaghetti", brand="Barilla", nutrients={"fat": 2}
    )
    clock.advance(minutes=10)

    response = await patch(
        api,
        ben,
        product["id"],
        name="Spaghetti n.5",
        brand=None,
        quantity_text="500 g",
        nutrients={"kcal": 359, "fat": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["brand"], body["quantity_text"]) == ("Spaghetti n.5", None, "500 g")
    assert body["nutrients"] == NO_NUTRIENTS | {"kcal": 359}
    assert body["user_edited_fields"] == [
        "name",
        "brand",
        "nutrients.fat",
        "quantity_text",
        "nutrients.kcal",
    ]
    assert body["created_by"] == ref(anna)
    assert body["updated_by"] == ref(ben)
    assert body["updated_at"] == "2026-09-27T12:10:00Z"

    body = (await patch(api, ben, product["id"], pack_quantity=500, pack_unit="g")).json()
    assert (body["pack_quantity"], body["pack_unit"]) == (500, "g")
    body = (await patch(api, ben, product["id"], pack_unit=None, nutrients=None)).json()
    assert body["pack_unit"] is None
    assert body["pack_quantity"] == 500
    assert body["user_edited_fields"][-2:] == ["pack_quantity", "pack_unit"]


async def test_change_the_barcode(api: AsyncClient, anna: Account, pasta: Any) -> None:
    first = await create_product(api, anna, pasta["id"], EAN_13)
    second = await create_product(api, anna, pasta["id"], EAN_8)

    taken = await patch(api, anna, second["id"], barcode=EAN_13)
    assert fields(taken) == {("body", "barcode"): "taken"}
    invalid = await patch(api, anna, second["id"], barcode="123")
    assert fields(invalid) == {("body", "barcode"): "invalid_format"}
    same = await patch(api, anna, first["id"], barcode=f" {EAN_13}")
    assert same.status_code == 200
    changed = await patch(api, anna, second["id"], barcode=UPC_A)
    assert changed.json()["barcode"] == f"0{UPC_A}"
    in_another_form = await patch(api, anna, first["id"], barcode=f"0{UPC_A}")
    assert fields(in_another_form) == {("body", "barcode"): "taken"}
    assert changed.json()["user_edited_fields"] == []


async def test_relink_to_another_ingredient(
    api: AsyncClient, anna: Account, pasta: Any, milk: Any
) -> None:
    rice = await create_ingredient(api, anna, "Reis")
    product = await create_product(api, anna, pasta["id"], EAN_13, nutrients={"kcal": 350})

    moved = await patch(api, anna, product["id"], ingredient_id=rice["id"])
    assert moved.status_code == 200
    assert moved.json()["ingredient_id"] == rice["id"]
    assert (await api.get(f"/api/ingredients/{rice['id']}", headers=anna.headers)).json()[
        "nutrition"
    ]["kcal"]["value"] == 350
    assert (await api.get(f"/api/ingredients/{pasta['id']}", headers=anna.headers)).json()[
        "product_count"
    ] == 0

    mismatch = await patch(api, anna, product["id"], ingredient_id=milk["id"])
    assert mismatch.status_code == 409
    assert error(mismatch) == "product.basis_mismatch"
    with_basis = await patch(
        api, anna, product["id"], ingredient_id=milk["id"], nutrition_basis="ml"
    )
    assert with_basis.status_code == 200
    assert with_basis.json()["nutrition_basis"] == "ml"
    assert with_basis.json()["user_edited_fields"] == ["nutrients.kcal", "nutrition_basis"]

    alone = await patch(api, anna, product["id"], nutrition_basis="g")
    assert error(alone) == "product.basis_mismatch"
    unknown = await patch(api, anna, product["id"], ingredient_id="nope")
    assert fields(unknown) == {("body", "ingredient_id"): "invalid"}


async def test_null_is_refused_for_required_fields(
    api: AsyncClient, anna: Account, ben: Account, pasta: Any, clock: FakeClock
) -> None:
    product = await create_product(api, anna, pasta["id"], EAN_13)
    clock.advance(minutes=1)
    response = await patch(
        api, ben, product["id"], barcode=None, ingredient_id=None, nutrition_basis=None
    )
    assert response.status_code == 422
    assert error(response) == "common.validation"
    assert fields(response) == {
        ("body", "barcode"): "invalid",
        ("body", "ingredient_id"): "invalid",
        ("body", "nutrition_basis"): "invalid",
    }
    for field in ("barcode", "ingredient_id", "nutrition_basis"):
        alone = await patch(api, ben, product["id"], **{field: None})
        assert fields(alone) == {("body", field): "invalid"}
    unchanged = await api.get(f"/api/products/{product['id']}", headers=anna.headers)
    assert unchanged.json() == product
