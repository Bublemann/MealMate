"""Open Food Facts data is untrusted: validated and cleaned before anything uses it (BAR-10)."""

import math
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.catalog import clean_text, cut_at_word
from app.domain.units import BaseUnit
from app.integrations.off import OffProduct

ALL_NUTRIENTS = {
    "energy-kcal_100g": 372,
    "proteins_100g": 13.5,
    "carbohydrates_100g": 58.7,
    "sugars_100g": 0.7,
    "fat_100g": 7,
}


def product(**raw: Any) -> OffProduct:
    return OffProduct.model_validate(raw)


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        ("Haferflocken", 20, "Haferflocken"),
        ("  Hafer \n\t flocken  ", 20, "Hafer flocken"),
        ("‮Snack\x00 with\x07 ​hidden⁦ characters", 50, "Snack with hidden characters"),
        ("x" * 30, 10, "x" * 10),
        ("ab   cdef", 3, "ab"),
        ("Hafer\ud800flocken\udfff", 20, "Haferflocken"),
        ("Apple \uf8ff Juice\U000f0000\u0378", 20, "Apple Juice"),
        ("\x00‮ \n", 10, None),
        ("", 10, None),
    ],
)
def test_clean_text(text: str, max_length: int, expected: str | None) -> None:
    assert clean_text(text, max_length) == expected


@pytest.mark.parametrize(
    ("text", "max_length", "expected"),
    [
        ("Haferflocken", 12, "Haferflocken"),
        ("Bio Vollmilch 3,8 % Fett", 20, "Bio Vollmilch 3,8 %"),
        ("Tomaten, passiert und fein", 20, "Tomaten, passiert"),
        ("Tomaten, passierte", 10, "Tomaten"),
        ("Superlangesproduktwort", 10, "Superlange"),
        ("A Superlangesproduktwort", 10, "A Superlan"),
    ],
)
def test_cut_at_word(text: str, max_length: int, expected: str) -> None:
    """Long names are cut at a word boundary, unless that loses more than half."""
    assert cut_at_word(text, max_length) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("4006381333931", "4006381333931"),
        ("036000291452", "0036000291452"),
        ("4006381333932", None),
        ("", None),
        (4006381333931, None),
        ("4" * 40, None),
    ],
)
def test_code_is_a_canonical_barcode(code: Any, expected: str | None) -> None:
    assert product(code=code).code == expected


def test_empty_product() -> None:
    empty = product()
    assert empty.name("de") is None
    assert (empty.brands, empty.quantity) == (None, None)
    assert empty.pack == (None, None)
    assert empty.nutrition_basis is None
    assert empty.nutrients == dict.fromkeys(("kcal", "protein", "carbs", "sugar", "fat"))
    assert empty.category_key is None
    assert empty.last_modified_at is None
    assert empty.fields("de") == {
        "name": None,
        "brand": None,
        "quantity_text": None,
        "pack_quantity": None,
        "pack_unit": None,
    }


@pytest.mark.parametrize(
    ("raw", "language", "expected"),
    [
        ({"product_name": "Oats", "product_name_de": "Hafer"}, "de", "Hafer"),
        ({"product_name": "Oats", "product_name_de": "Hafer"}, "en", "Oats"),
        ({"product_name": "Oats", "product_name_en": "Rolled oats"}, "en", "Rolled oats"),
        ({"product_name_de": " ​ ", "product_name": "Oats"}, "de", "Oats"),
        ({"generic_name": "Oat flakes", "generic_name_de": "Haferflocken"}, "de", "Haferflocken"),
        ({"generic_name": "Oat flakes", "product_name": ""}, "de", "Oat flakes"),
        ({"product_name_fr": "Flocons"}, "de", None),
        ({"product_name": 42, "generic_name": ["x"]}, "de", None),
    ],
)
def test_name_in_the_users_language(raw: dict[str, Any], language: str, expected: str) -> None:
    assert product(**raw).name(language) == expected


def test_texts_are_cleaned_and_capped() -> None:
    hostile = product(
        product_name="‮Evil\x00 " + "n" * 300,
        brands="Evil Corp " + "X" * 200,
        quantity="1‮00 g" + " " * 100 + "x" * 100,
        extra_field={"ignored": True},
    )
    name = hostile.name("de")
    assert name is not None
    assert name.startswith("Evil nnn")
    assert len(name) == 60
    assert hostile.brands == "Evil Corp " + "X" * 70
    assert hostile.quantity == "100 g " + "x" * 34


@pytest.mark.parametrize(
    ("nutriments", "expected"),
    [
        (ALL_NUTRIENTS, {"kcal": 372, "protein": 13.5, "carbs": 58.7, "sugar": 0.7, "fat": 7}),
        (
            {
                "energy-kcal_100g": 99999,
                "proteins_100g": -5,
                "carbohydrates_100g": "12.5",
                "sugars_100g": True,
                "fat_100g": "NaN",
            },
            {"kcal": None, "protein": None, "carbs": 12.5, "sugar": None, "fat": None},
        ),
        (
            {
                "energy-kcal_100g": 900,
                "proteins_100g": 0,
                "carbohydrates_100g": float("inf"),
                "sugars_100g": "1" * 40,
                "fat_100g": "fat",
            },
            {"kcal": 900, "protein": 0, "carbs": None, "sugar": None, "fat": None},
        ),
        (
            {"energy-kcal_100g": 10**400, "proteins_100g": " 3 ", "fat_100g": "1e999"},
            {"kcal": None, "protein": 3, "carbs": None, "sugar": None, "fat": None},
        ),
        (
            {"energy-kcal": 200, "proteins_100g": {"value": 3}, "fat_100g": None},
            {"kcal": None, "protein": None, "carbs": None, "sugar": None, "fat": None},
        ),
        ("not an object", dict.fromkeys(("kcal", "protein", "carbs", "sugar", "fat"))),
    ],
)
def test_nutrients_must_be_finite_and_plausible(
    nutriments: Any, expected: dict[str, float | None]
) -> None:
    assert product(nutriments=nutriments, nutrition_data_per="100g").nutrients == expected


def test_negative_zero_is_zero() -> None:
    """`-0` would be shown as "-0" (and 0.0 == -0.0 hides it from comparisons)."""
    found = product(
        nutriments={"energy-kcal_100g": -0.0, "fat_100g": "-0", "sugars_100g": "-0.000"},
        nutrition_data_per="100g",
    )
    assert found.nutriments == {"kcal": 0, "sugar": 0, "fat": 0}
    assert [math.copysign(1, value) for value in found.nutriments.values()] == [1, 1, 1]


@pytest.mark.parametrize(
    ("per", "unit", "expected"),
    [
        ("100g", "g", BaseUnit.G),
        ("100g", None, BaseUnit.G),
        # OFF's `_100g` values are per 100 ml for products sold by volume.
        ("100g", "ml", BaseUnit.ML),
        ("100ml", "g", BaseUnit.ML),
        (" 100 G ", "g", BaseUnit.G),
        ("serving", "g", None),
        ("per pack", "g", None),
        (None, "g", None),
        (100, "g", None),
    ],
)
def test_nutrition_basis(per: Any, unit: str | None, expected: BaseUnit | None) -> None:
    found = product(
        nutrition_data_per=per,
        nutriments=ALL_NUTRIENTS,
        product_quantity=500,
        product_quantity_unit=unit,
    )
    assert found.nutrition_basis is expected
    # Without a basis the values are unknown, never guessed.
    assert (found.nutrients["kcal"] is None) is (expected is None)
    assert ("nutrients.kcal" in found.fields("de")) is (expected is not None)


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (500, "g", (500, BaseUnit.G)),
        ("1000", "ml", (1000, BaseUnit.ML)),
        ("0.75", " ML ", (None, None)),
        (250, " ml ", (250, BaseUnit.ML)),
        (250, "mlx", (None, None)),
        (250, "gram", (None, None)),
        (250, "g" + " " * 20 + "x", (None, None)),
        (250, 1, (None, None)),
        (500, "kg", (None, None)),
        # Pieces are a base unit, not a pack unit Open Food Facts gives (D-38).
        (6, "piece", (None, None)),
        (500, None, (None, None)),
        (None, "g", (None, None)),
        (0, "g", (None, None)),
        (-3, "g", (None, None)),
        (100_001, "g", (None, None)),
        (True, "g", (None, None)),
        ([500], "g", (None, None)),
    ],
)
def test_pack_size(quantity: Any, unit: Any, expected: tuple[Any, Any]) -> None:
    assert product(product_quantity=quantity, product_quantity_unit=unit).pack == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1767225600, datetime(2026, 1, 1, tzinfo=UTC)),
        ("1767225600", datetime(2026, 1, 1, tzinfo=UTC)),
        (1767225600.9, datetime(2026, 1, 1, tzinfo=UTC)),
        ("not a timestamp", None),
        (0, None),
        (-1, None),
        (99_999_999_999, None),
        (None, None),
    ],
)
def test_last_modified(value: Any, expected: datetime | None) -> None:
    assert product(last_modified_t=value).last_modified_at == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["en:dairies", "en:cheeses"], "cheese"),
        (["en:snacks", 42, None, "‮en:sweets"], "snacks_sweets"),
        (["en:plant-based-foods"], None),
        ("en:cheeses", None),
        ([f"en:tag-{index}" for index in range(300)] + ["en:cheeses"], None),
    ],
)
def test_category_from_tags(tags: Any, expected: str | None) -> None:
    assert product(categories_tags=tags).category_key == expected


def test_fields_by_product_field() -> None:
    found = product(
        product_name="Rolled Oats",
        product_name_de="Haferflocken",
        brands="Test Kitchen",
        quantity="500 g",
        product_quantity=500,
        product_quantity_unit="g",
        nutrition_data_per="100g",
        nutriments=ALL_NUTRIENTS | {"fat_100g": 101},
    )
    assert found.fields("de") == {
        "name": "Haferflocken",
        "brand": "Test Kitchen",
        "quantity_text": "500 g",
        "pack_quantity": 500,
        "pack_unit": "g",
        "nutrients.kcal": 372,
        "nutrients.protein": 13.5,
        "nutrients.carbs": 58.7,
        "nutrients.sugar": 0.7,
        "nutrients.fat": None,
    }
