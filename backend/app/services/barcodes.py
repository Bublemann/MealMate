"""The barcode lookup (BAR-02, BAR-03, plan § 5.9): our own products first, then Open Food Facts.

A barcode we know goes straight to its product and ingredient. Otherwise Open Food Facts is
asked, outside any transaction, and its product becomes a *proposal* that is not saved: the
user picks or creates the ingredient ("Which ingredient is this?", with name-matched
suggestions) and may correct values before saving it with `POST /api/products`.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    validation_error,
)
from app.domain.barcodes import normalize_barcode
from app.domain.units import Unit
from app.integrations.off import LOOKUP_MAX_WAIT_SECONDS, OffClient, OffProduct
from app.repositories import ingredients as ingredients_repo
from app.repositories import products as products_repo
from app.repositories import users as users_repo
from app.schemas.nutrition import NutrientValues
from app.schemas.products import ProductLookup, ProductProposal
from app.services import ingredients, products
from app.services.off_refresh import DEFAULT_LANGUAGE
from app.services.principal import Principal
from app.services.products import base_unit_name


def proposal(found: OffProduct, language: str) -> ProductProposal:
    """The API view of a product from Open Food Facts, named in `language` if possible."""
    pack_quantity, pack_unit = found.pack
    basis = found.nutrition_basis
    return ProductProposal(
        name=found.name(language),
        brand=found.brands,
        quantity_text=found.quantity,
        pack_quantity=pack_quantity,
        pack_unit=None if pack_unit is None else Unit(pack_unit.value),
        nutrition_basis=None if basis is None else base_unit_name(basis.value),
        nutrients=NutrientValues.model_validate(found.nutrients),
        category_key=found.category_key,
        off_last_modified_at=found.last_modified_at,
    )


def _nothing(barcode: str, *, off_unavailable: bool) -> ProductLookup:
    return ProductLookup(
        barcode=barcode,
        found_in="none",
        product=None,
        ingredient=None,
        proposal=None,
        suggestions=[],
        off_unavailable=off_unavailable,
    )


async def lookup(
    session: AsyncSession, off: OffClient, principal: Principal, text: str
) -> ProductLookup:
    """Look a barcode up (422 `invalid_format` if it is not a valid EAN/UPC code): a product
    of ours, else Open Food Facts' proposal with suggestions, else nothing (after a transient
    failure, Open Food Facts gets a second try before that, see `OffClient.fetch`). While too
    many lookups wait for Open Food Facts: 503 `off.busy`."""
    barcode = normalize_barcode(text)
    if barcode is None:
        raise validation_error([FieldProblem(("query", "barcode"), FieldErrorCode.INVALID_FORMAT)])
    async with session.begin():
        row = await products_repo.by_barcode(session, barcode)
        if row is not None:
            [(ingredient, count)] = (
                await ingredients_repo.with_product_counts(session, [row.ingredient_id])
            ).values()
            return ProductLookup(
                barcode=barcode,
                found_in="db",
                product=(await products.products(session, [row]))[0],
                ingredient=ingredients.summary(ingredient, count),
                proposal=None,
                suggestions=[],
                off_unavailable=False,
            )
        user = await users_repo.get(session, principal.user_id)
        language = user.language if user is not None else DEFAULT_LANGUAGE

    # The user waits for this answer: a transient failure gets a second try, "not found" none.
    response = await off.fetch(barcode, max_wait=LOOKUP_MAX_WAIT_SECONDS, retry=True)
    if response.status == "busy":
        raise ApiError(ErrorCode.OFF_BUSY, status_code=503)
    if response.product is None:
        return _nothing(barcode, off_unavailable=response.status == "unavailable")
    found = proposal(response.product, language)
    return ProductLookup(
        barcode=barcode,
        found_in="off",
        product=None,
        ingredient=None,
        proposal=found,
        suggestions=await ingredients.similar(session, found.name) if found.name else [],
        off_unavailable=False,
    )
