"""Products: barcodes linked to an ingredient, entered by hand (ING-04, BAR-04).

Everyone may add and edit products (plan § 5.5). A product's nutrition basis is always its
ingredient's base unit. Every data field a user sets is marked user-edited, so that an Open
Food Facts refresh (M7) never overwrites it. The barcode and the ingredient link are not data
from Open Food Facts and are never marked.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    not_found,
    validation_error,
)
from app.domain.barcodes import normalize_barcode
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize
from app.domain.units import Unit
from app.models import Ingredient as IngredientRow
from app.models import Product as ProductRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import products as products_repo
from app.schemas.ingredients import BaseUnitName
from app.schemas.nutrition import NutrientValues
from app.schemas.products import Product, ProductCreate, ProductSource, ProductUpdate
from app.schemas.users import UserRef
from app.services.principal import Principal
from app.services.users import user_refs

# Product fields that hold data (as opposed to the barcode and the ingredient link); each one
# a user sets becomes user-edited, and nutrients are marked as `nutrients.<key>`.
DATA_FIELDS = ("nutrition_basis", "name", "brand", "quantity_text", "pack_quantity", "pack_unit")
_TEXT_AND_NUMBER_FIELDS = ("name", "brand", "quantity_text", "pack_quantity")


def base_unit_name(value: str) -> BaseUnitName:
    return "ml" if value == "ml" else "g"


def _source(value: str) -> ProductSource:
    return "off" if value == "off" else "manual"


def product(row: ProductRow, refs: dict[str, UserRef]) -> Product:
    return Product(
        id=row.id,
        barcode=row.barcode,
        ingredient_id=row.ingredient_id,
        nutrition_basis=base_unit_name(row.nutrition_basis),
        name=row.name,
        brand=row.brand,
        quantity_text=row.quantity_text,
        pack_quantity=row.pack_quantity,
        pack_unit=None if row.pack_unit is None else Unit(row.pack_unit),
        nutrients=NutrientValues.model_validate(row.nutrients()),
        source=_source(row.source),
        user_edited_fields=list(row.user_edited_fields),
        fetched_at=row.fetched_at,
        created_by=refs.get(row.created_by) if row.created_by else None,
        updated_by=refs.get(row.updated_by) if row.updated_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _display_order(row: ProductRow) -> tuple[bool, str, str]:
    """By name (products without one last), then barcode."""
    return (row.name is None, normalize(row.name or ""), row.barcode)


async def products(session: AsyncSession, rows: Sequence[ProductRow]) -> list[Product]:
    """The API view of `rows`, by name and barcode."""
    refs = await user_refs(
        session, [user for row in rows for user in (row.created_by, row.updated_by)]
    )
    return [product(row, refs) for row in sorted(rows, key=_display_order)]


def _barcode(text: str) -> str:
    barcode = normalize_barcode(text)
    if barcode is None:
        raise validation_error([FieldProblem(("body", "barcode"), FieldErrorCode.INVALID_FORMAT)])
    return barcode


def _check_basis(basis: str, ingredient: IngredientRow) -> None:
    if basis != ingredient.base_unit:
        raise ApiError(ErrorCode.PRODUCT_BASIS_MISMATCH, status_code=409)


def _nutrient_fields(values: NutrientValues | None, keys: Iterable[str]) -> list[str]:
    return [] if values is None else [f"nutrients.{key}" for key in keys]


async def create_product(
    session: AsyncSession, principal: Principal, body: ProductCreate, *, now: datetime
) -> Product:
    """Add a product by hand (`source` manual). The basis defaults to the ingredient's base
    unit; every field given (not null) is marked user-edited."""
    barcode = _barcode(body.barcode)
    async with session.begin():
        problems: list[FieldProblem] = []
        if await products_repo.barcode_taken(session, barcode):
            problems.append(FieldProblem(("body", "barcode"), FieldErrorCode.TAKEN))
        ingredient = await ingredients_repo.get(session, body.ingredient_id)
        if ingredient is None:
            problems.append(FieldProblem(("body", "ingredient_id"), FieldErrorCode.INVALID))
        if problems or ingredient is None:
            raise validation_error(problems)
        basis = body.nutrition_basis or ingredient.base_unit
        _check_basis(basis, ingredient)
        given = body.model_dump(include=set(DATA_FIELDS), exclude_none=True)
        nutrients = {} if body.nutrients is None else body.nutrients.model_dump()
        row = ProductRow(
            barcode=barcode,
            ingredient_id=ingredient.id,
            nutrition_basis=basis,
            name=body.name,
            brand=body.brand,
            quantity_text=body.quantity_text,
            pack_quantity=body.pack_quantity,
            pack_unit=None if body.pack_unit is None else body.pack_unit.value,
            source="manual",
            user_edited_fields=[
                *(field for field in DATA_FIELDS if field in given),
                *_nutrient_fields(
                    body.nutrients, (key for key, value in nutrients.items() if value is not None)
                ),
            ],
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        row.set_nutrients(NutrientValues().model_dump() | nutrients)
        session.add(row)
        await session.flush()
        return (await products(session, [row]))[0]


async def get_product(session: AsyncSession, product_id: str) -> Product:
    async with session.begin():
        row = await products_repo.get(session, product_id)
        if row is None:
            raise not_found()
        return (await products(session, [row]))[0]


async def update_product(
    session: AsyncSession,
    principal: Principal,
    product_id: str,
    body: ProductUpdate,
    *,
    now: datetime,
) -> Product:
    """Change the fields that were sent (null clears an optional one) and mark them
    user-edited (BAR-04). A new `ingredient_id` relinks the product; the basis must match the
    (new) ingredient's base unit."""
    sent = body.model_fields_set
    barcode = None if body.barcode is None else _barcode(body.barcode)
    async with session.begin():
        row = await products_repo.get(session, product_id)
        if row is None:
            raise not_found()
        problems: list[FieldProblem] = []
        if barcode is not None and await products_repo.barcode_taken(
            session, barcode, except_id=row.id
        ):
            problems.append(FieldProblem(("body", "barcode"), FieldErrorCode.TAKEN))
        ingredient = await ingredients_repo.get(session, body.ingredient_id or row.ingredient_id)
        if ingredient is None:
            problems.append(FieldProblem(("body", "ingredient_id"), FieldErrorCode.INVALID))
        if problems or ingredient is None:
            raise validation_error(problems)
        basis = body.nutrition_basis or row.nutrition_basis
        _check_basis(basis, ingredient)

        if barcode is not None:
            row.barcode = barcode
        row.ingredient_id = ingredient.id
        row.nutrition_basis = basis
        for field in _TEXT_AND_NUMBER_FIELDS:
            if field in sent:
                setattr(row, field, getattr(body, field))
        if "pack_unit" in sent:
            row.pack_unit = None if body.pack_unit is None else body.pack_unit.value
        nutrient_keys = (
            []
            if body.nutrients is None
            else [key for key in NUTRIENT_KEYS if key in body.nutrients.model_fields_set]
        )
        for key in nutrient_keys:
            row.set_nutrient(key, getattr(body.nutrients, key))
        edited = [field for field in DATA_FIELDS if field in sent]
        edited += _nutrient_fields(body.nutrients, nutrient_keys)
        row.user_edited_fields = list(dict.fromkeys([*row.user_edited_fields, *edited]))
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return (await products(session, [row]))[0]
